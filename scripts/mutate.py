# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Kill behavioral mutants using isolated sources and measured golden or regression tests."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NoReturn

from rich.console import Console

from datakeel.core.harness_eval import EvalCaseResult, EvalReport
from scripts.core_mutations import CORE_MUTATIONS
from scripts.mutation_catalog import FEATURE_MUTATIONS
from scripts.mutation_models import Mutation, MutationResult, TestMeasurement
from scripts.mutation_parallel import ordered_parallel_map
from scripts.mutation_shards import select_mutations
from scripts.mutation_timeouts import EnvironmentFailure, retry_on_timeout
from scripts.shard_spec import parse_shard
from scripts.test_workers import test_worker_count
from scripts.workflow_mutations import WORKFLOW_MUTATIONS

ROOT = Path(__file__).resolve().parents[1]
# Hang bounds only: CI runners are slow, and golden evaluations share them with other workers.
SUBPROCESS_TIMEOUT_SECONDS = 300
EVAL_TIMEOUT_SECONDS = 900


MUTATIONS = (
    *CORE_MUTATIONS,
    *WORKFLOW_MUTATIONS,
    *FEATURE_MUTATIONS,
)


def _copy_source(target: Path) -> None:
    shutil.copytree(
        ROOT / "datakeel",
        target / "datakeel",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "web_dist", "_contracts"),
    )
    shutil.copytree(ROOT / "contracts", target / "contracts")
    shutil.copytree(ROOT / "docs" / "p9", target / "docs" / "p9")
    shutil.copytree(
        ROOT / "tests", target / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )


def local_environment(directory: Path) -> dict[str, str]:
    """Remove inherited service settings and credentials before binding isolated local stores."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_"))
    }
    environment.update(
        {
            "PYTHONPATH": str(directory),
            "DATAKEEL_HOME": str(directory / "home"),
            "DATAKEEL_DATABASE_URL": f"sqlite:///{directory / 'evaluation.db'}",
            "DATAKEEL_ACCEL": "off",
            "DATAKEEL_OPENAI_API_KEY": "",
            "DATAKEEL_ANTHROPIC_API_KEY": "",
        }
    )
    return environment


def _evaluate(directory: Path) -> tuple[int, EvalReport]:
    process = subprocess.run(  # Fixed interpreter/module; no shell or external input.
        [sys.executable, "-m", "datakeel.cli", "eval", "--provider", "fake", "--json"],
        cwd=directory,
        env=local_environment(directory),
        capture_output=True,
        text=True,
        timeout=EVAL_TIMEOUT_SECONDS,
        check=False,
    )
    if process.returncode not in (0, 1):
        msg = f"Evaluation process crashed: {process.stderr[-2000:]}"
        raise RuntimeError(msg)
    try:
        return process.returncode, EvalReport.model_validate_json(process.stdout)
    except ValueError as error:
        msg = f"Evaluation returned no measured report: {process.stderr[-2000:]}"
        raise RuntimeError(msg) from error


def _missing_authorization_assertion(failure: ET.Element) -> bool:
    text = failure.text or ""
    return (
        failure.attrib.get("message") == "Failed: DID NOT RAISE AuthorizationError"
        and "type" not in failure.attrib
        and "with pytest.raises(AuthorizationError" in text
        and any(
            line.split() == ["E", "Failed:", "DID", "NOT", "RAISE", "AuthorizationError"]
            for line in text.splitlines()
        )
    )


def evaluate_image_test(directory: Path, node_id: str) -> TestMeasurement:
    """Accept only one declared test's call assertion, rejecting crashes and setup failures."""
    report = directory / "test-results.xml"
    process = subprocess.run(  # noqa: S603  # Fixed interpreter; repository-owned node id, no shell.
        [sys.executable, "-m", "pytest", "-n", "0", node_id, "-q", f"--junitxml={report}"],
        cwd=directory,
        env=local_environment(directory),
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    if process.returncode not in (0, 1) or not report.is_file():
        msg = f"Image test process crashed: {process.stderr[-2000:]} {process.stdout[-2000:]}"
        raise RuntimeError(msg)
    # Pytest in the immediately preceding local subprocess generated this report.
    root = ET.fromstring(report.read_text())  # noqa: S314
    cases = root.findall(".//testcase")
    if len(cases) != 1 or root.findall(".//error") or root.findall(".//skipped"):
        msg = "Image test did not produce exactly one measured call outcome"
        raise RuntimeError(msg)
    target_path, target_name = node_id.split("::")
    case = cases[0]
    if case.attrib.get("name") != target_name or case.attrib.get(
        "classname"
    ) != target_path.removesuffix(".py").replace("/", "."):
        msg = "Image test report does not match the declared target"
        raise RuntimeError(msg)
    failure = case.find("failure")
    detail = (
        "" if failure is None else (failure.attrib.get("message", "") + "\n" + (failure.text or ""))
    )
    if (
        failure is not None
        and "AssertionError" not in detail
        and not _missing_authorization_assertion(failure)
    ):
        msg = f"Image test failed outside its assertion: {detail[-2000:]}"
        raise RuntimeError(msg)
    return TestMeasurement(
        exit_code=process.returncode,
        passed=int(failure is None),
        total=1,
        failures={node_id: [detail]} if failure is not None else {},
    )


def explanation_failure(code: int, result: EvalCaseResult) -> bool:
    """Require an actual successful explanation whose observed payload fails its golden schema."""
    explanations = [item for item in result.tool_results if item.name == "explain_sample"]
    return (
        code == 1
        and not result.passed
        and result.fixture_error is None
        and result.tool_sequence == ["explain_sample"]
        and len(explanations) == 1
        and explanations[0].status == "SUCCEEDED"
        and any(
            failure.startswith("Tool content mismatch: explain_sample at data.states:")
            for failure in result.failures
        )
    )


def measure_unknown_mutation(
    mutation: Mutation, directory: Path, code: int, report: EvalReport
) -> MutationResult:
    """Measure the production boundary and, with an explicit temporary bypass, the explanation."""
    boundary = next(case for case in report.cases if case.id == mutation.case)
    boundary_rejected = (
        code == 1
        and not boundary.passed
        and not boundary.tool_sequence
        and "Only directly measured corruption may assert absence" in (boundary.fixture_error or "")
    )
    explanation, probe_code, bypass = None, None, None
    if boundary_rejected:
        path = directory / "datakeel/core/evidence_models.py"
        before = 'elif self.object.value == "absent" and self.predicate != "corrupt":'
        after = (
            'elif self.object.value == "absent" and self.predicate not in {"corrupt", "label_gap"}:'
        )
        original = path.read_text(encoding="utf-8")
        if original.count(before) != 1:
            msg = "Deep explanation probe requires exactly one production absence guard"
            raise RuntimeError(msg)
        # Only the isolated mutant copy admits malformed label_gap values for this deeper probe.
        path.write_text(original.replace(before, after), encoding="utf-8")
        bypass = "Temporary mutant copy only: admit label_gap=absent past Assertion validation."
        probe_code, probe = _evaluate(directory)
        explanation = next(case for case in probe.cases if case.id == mutation.case)
    return MutationResult(
        name=mutation.name,
        killed=boundary_rejected
        and explanation is not None
        and probe_code is not None
        and explanation_failure(probe_code, explanation),
        passed=report.passed,
        total=report.total,
        failures={case.id: case.failures for case in report.cases if not case.passed},
        target=mutation.case,
        boundary_case=boundary,
        explanation_case=explanation,
        explanation_probe_exit=probe_code,
        validation_bypass=bypass,
    )


def run_mutation(mutation: Mutation) -> MutationResult:
    """Apply a guard change only in a fresh temporary source tree and run all goldens."""
    with TemporaryDirectory(prefix="datakeel-mutation-") as temporary:
        directory = Path(temporary)
        _copy_source(directory)
        path = directory / "datakeel" / mutation.path
        original = path.read_text(encoding="utf-8")
        if original.count(mutation.before) != 1:
            msg = f"Mutation anchor must occur once: {mutation.name}"
            raise RuntimeError(msg)
        path.write_text(original.replace(mutation.before, mutation.after), encoding="utf-8")
        if mutation.runner == "pytest":
            measured = evaluate_image_test(directory, mutation.case)
        else:
            code, report = _evaluate(directory)
            if mutation.name == "missing-annotation-unknown":
                return measure_unknown_mutation(mutation, directory, code, report)
            measured = TestMeasurement(
                exit_code=code,
                passed=report.passed,
                total=report.total,
                failures={case.id: case.failures for case in report.cases if not case.passed},
            )
        return MutationResult(
            name=mutation.name,
            killed=measured.exit_code == 1 and mutation.case in measured.failures,
            passed=measured.passed,
            total=measured.total,
            failures=measured.failures,
            runner=mutation.runner,
            target=mutation.case,
        )


def evaluate_image_baseline(node_id: str) -> TestMeasurement:
    """Measure one unchanged pytest target in its own disposable source tree."""
    with TemporaryDirectory(prefix="datakeel-mutation-baseline-") as temporary:
        directory = Path(temporary)
        _copy_source(directory)
        return evaluate_image_test(directory, node_id)


def evaluate_golden_baseline() -> tuple[int, EvalReport]:
    """Measure every unchanged golden case in its own disposable source tree."""
    with TemporaryDirectory(prefix="datakeel-mutation-baseline-") as temporary:
        directory = Path(temporary)
        _copy_source(directory)
        return _evaluate(directory)


def _finish(
    output: Path | None,
    report: dict[str, object],
    failures: list[EnvironmentFailure],
    *,
    killed: bool,
) -> NoReturn:
    """Write the report even for environment failures, then exit without a stack trace."""
    if failures:
        report["environment_failures"] = [failure.model_dump(mode="json") for failure in failures]
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for failure in failures:
        Console(soft_wrap=True).print(failure.describe(), markup=False, highlight=False)
    raise SystemExit(not killed or bool(failures))


def _measure_image_baselines(
    mutations: tuple[Mutation, ...], workers: int
) -> list[TestMeasurement | EnvironmentFailure]:
    return list(
        ordered_parallel_map(
            lambda case: retry_on_timeout(
                lambda: evaluate_image_baseline(case), f"pytest baseline {case}"
            ),
            (mutation.case for mutation in mutations if mutation.runner == "pytest"),
            workers=workers,
        )
    )


def main() -> None:
    """Require green baselines and observed assertion failures with durable evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--shard", type=parse_shard, help="Run only catalog shard K of N (K/N).")
    args = parser.parse_args()
    mutations = MUTATIONS if args.shard is None else select_mutations(MUTATIONS, args.shard)
    workers = test_worker_count()
    report: dict[str, object] = {} if args.shard is None else {"shard": str(args.shard)}
    golden = retry_on_timeout(evaluate_golden_baseline, "golden baseline")
    if isinstance(golden, EnvironmentFailure):
        empty = {"baseline": None, "image_baselines": [], "mutations": []}
        _finish(args.output, report | empty, [golden], killed=False)
    code, baseline = golden
    if code != 0 or baseline.passed != baseline.total:
        msg = "Golden baseline must pass before mutation testing"
        raise RuntimeError(msg)
    measured = _measure_image_baselines(mutations, workers)
    failures = [item for item in measured if isinstance(item, EnvironmentFailure)]
    image_baselines = [item for item in measured if isinstance(item, TestMeasurement)]
    report["baseline"] = baseline.model_dump(mode="json")
    report["image_baselines"] = [result.model_dump(mode="json") for result in image_baselines]
    if failures:
        _finish(args.output, report | {"mutations": []}, failures, killed=False)
    if any(result.exit_code != 0 or result.passed != result.total for result in image_baselines):
        msg = "Image baseline must pass before mutation testing"
        raise RuntimeError(msg)
    results: list[MutationResult] = []
    outcomes = ordered_parallel_map(
        lambda mutation: retry_on_timeout(
            lambda: run_mutation(mutation), f"mutation {mutation.name}"
        ),
        mutations,
        workers=workers,
    )
    for mutation, outcome in zip(mutations, outcomes, strict=True):
        if isinstance(outcome, EnvironmentFailure):
            failures.append(outcome)
            status = "ENVIRONMENT FAILURE (timed out twice)"
        else:
            results.append(outcome)
            status = (
                f"{'KILLED' if outcome.killed else 'SURVIVED'} "
                f"({outcome.passed}/{outcome.total} {outcome.runner} cases passed)"
            )
        Console().print(f"{mutation.name}: {status}")
    report["mutations"] = [result.model_dump(mode="json") for result in results]
    _finish(args.output, report, failures, killed=all(result.killed for result in results))


if __name__ == "__main__":
    main()
