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

from rich.console import Console

from datakeel.core.harness_eval import EvalCaseResult, EvalReport
from scripts.advanced_mutations import ADVANCED_MUTATIONS
from scripts.dq_mutations import DQ_MUTATIONS
from scripts.image_kg_mutations import IMAGE_KG_MUTATIONS
from scripts.kg_mutations import KG_MUTATIONS
from scripts.knowledge_mutations import KNOWLEDGE_MUTATIONS
from scripts.mutation_models import Mutation, MutationResult, TestMeasurement
from scripts.workflow_mutations import WORKFLOW_MUTATIONS

ROOT = Path(__file__).resolve().parents[1]
# Shared CI runners can be several times slower than a laptop; this only bounds hangs.
SUBPROCESS_TIMEOUT_SECONDS = 300


MUTATIONS = (
    Mutation(
        name="resume-authorization",
        path="runtime/graph.py",
        before=(
            "authorize_resume(self.db, self.conversation_id, request.plan_id, self.pending_plan())"
        ),
        after="pass",
        case="tests/agent/test_resume.py::test_forged_resume_cases_are_denied_and_audited",
        runner="pytest",
    ),
    Mutation(
        name="tool-call-idempotency",
        path="storage/tool_invocations.py",
        before="if call_id is None:",
        after="if True:",
        case=(
            "tests/runtime/test_recovery.py::"
            "test_recovery_when_killed_after_interrupt_preserves_one_action_and_tool_call"
        ),
        runner="pytest",
    ),
    Mutation(
        name="repeated-call",
        path="agent/guards.py",
        before="if self.calls[signature] >= REPEAT_LIMIT:",
        after="if False:",
        case="07-repeated-loop",
    ),
    Mutation(
        name="budget-reservation",
        path="storage/budget_service.py",
        before="exceeded = any(",
        after="exceeded = False and any(",
        case="08-budget",
    ),
    Mutation(
        name="dry-run", path="agent/confirm.py", before=" or dry_run:", after=":", case="11-dry-run"
    ),
    Mutation(
        name="human-approval",
        path="agent/confirm.py",
        before=" or plan.requires_approval",
        after="",
        case="04-irreversible-approval",
    ),
    Mutation(
        name="canonical-parameters",
        path="storage/action_requests.py",
        before="if request.canonical_params is not None and digest(request.canonical_params)",
        after="if False and digest(request.canonical_params)",
        case="06-frozen-approval",
    ),
    Mutation(
        name="target-state",
        path="storage/action_planning.py",
        before=(
            "if snapshot_digest(session, params, current) != plan.state_digest "
            "or current.truncated:"
        ),
        after="if False:",
        case="06-frozen-approval",
    ),
    Mutation(
        name="missing-annotation-unknown",
        path="operators/evidence/label_gap.py",
        before='value = "unknown"',
        after='value = "absent"',
        case="14-evidence-unknown",
    ),
    Mutation(
        name="near-duplicate-threshold",
        path="operators/evidence/near_duplicate.py",
        before="if distance <= contract.hamming_threshold:",
        after="if distance <= contract.hamming_threshold + 4:",
        case=(
            "tests/operators/evidence/test_near_duplicate.py::"
            "test_near_duplicate_when_chain_images_supplied_does_not_infer_endpoint_pair"
        ),
        runner="pytest",
    ),
    Mutation(
        name="model-sql-bypass",
        path="ask/rerank.py",
        before="allowed = set(original)",
        after="allowed = set(ranking.ordered_ids)",
        case="tests/ask/test_mutation_boundaries.py::test_model_sql_cannot_cross_candidate_id_boundary",
        runner="pytest",
    ),
    Mutation(
        name="unanswerable-guessed-answer",
        path="core/ask_models.py",
        before=(
            "if self.sql is not None or self.result is not None or self.metric_card is not None:"
        ),
        after="if False:",
        case=(
            "tests/ask/test_mutation_boundaries.py::"
            "test_unanswerable_cannot_publish_a_guessed_numeric_answer"
        ),
        runner="pytest",
    ),
    *WORKFLOW_MUTATIONS,
    *ADVANCED_MUTATIONS,
    *KG_MUTATIONS,
    *KNOWLEDGE_MUTATIONS,
    *IMAGE_KG_MUTATIONS,
    *DQ_MUTATIONS,
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
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
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


def evaluate_image_test(directory: Path, node_id: str) -> TestMeasurement:
    """Accept only one declared test's call assertion, rejecting crashes and setup failures."""
    report = directory / "test-results.xml"
    process = subprocess.run(  # noqa: S603  # Fixed interpreter; repository-owned node id, no shell.
        [sys.executable, "-m", "pytest", node_id, "-q", f"--junitxml={report}"],
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
    if failure is not None and "AssertionError" not in detail:
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


def main() -> None:
    """Require green baselines and observed assertion failures with durable evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="datakeel-mutation-baseline-") as temporary:
        directory = Path(temporary)
        _copy_source(directory)
        code, baseline = _evaluate(directory)
        if code != 0 or baseline.passed != baseline.total:
            msg = "Golden baseline must pass before mutation testing"
            raise RuntimeError(msg)
        image_baselines = [
            evaluate_image_test(directory, mutation.case)
            for mutation in MUTATIONS
            if mutation.runner == "pytest"
        ]
        if any(
            result.exit_code != 0 or result.passed != result.total for result in image_baselines
        ):
            msg = "Image baseline must pass before mutation testing"
            raise RuntimeError(msg)
    results = [run_mutation(mutation) for mutation in MUTATIONS]
    report = {
        "baseline": baseline.model_dump(mode="json"),
        "image_baselines": [result.model_dump(mode="json") for result in image_baselines],
        "mutations": [result.model_dump(mode="json") for result in results],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for result in results:
        Console().print(
            f"{result.name}: {'KILLED' if result.killed else 'SURVIVED'} "
            f"({result.passed}/{result.total} {result.runner} cases passed)"
        )
    raise SystemExit(not all(result.killed for result in results))


if __name__ == "__main__":
    main()
