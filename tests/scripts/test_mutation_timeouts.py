# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A timed-out mutation subprocess is retried once, then recorded without a crash."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import utcnow
from scripts import mutate
from scripts.mutation_models import Mutation, MutationResult
from scripts.mutation_models import TestMeasurement as Measurement
from scripts.mutation_timeouts import EnvironmentFailure, retry_on_timeout

ROOT = Path(__file__).resolve().parents[2]
EVAL_COMMAND = [sys.executable, "-m", "datakeel.cli", "eval", "--provider", "fake", "--json"]
_REAL_IMAGE_BASELINE = mutate.evaluate_image_baseline


def _timeout(timeout: float = 900) -> subprocess.TimeoutExpired:
    return subprocess.TimeoutExpired(cmd=EVAL_COMMAND, timeout=timeout)


def test_one_timeout_is_retried_and_the_second_measurement_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The retry gets a fresh attempt, and its real result replaces the timeout."""
    attempts: list[int] = []

    def measure() -> str:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise _timeout()
        return "measured"

    assert retry_on_timeout(measure, "mutation target") == "measured"
    assert attempts == [0, 1]
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    assert "Retrying mutation target: command" in output
    assert "datakeel.cli eval" in output


def test_two_timeouts_become_one_line_environment_failure() -> None:
    """The second timeout is evidence about the runner, named by target and command."""
    attempts: list[int] = []

    def measure() -> str:
        attempts.append(1)
        raise _timeout(300)

    failure = retry_on_timeout(measure, "mutation target")
    assert len(attempts) == 2
    assert isinstance(failure, EnvironmentFailure)
    assert failure.target == "mutation target"
    assert "-m datakeel.cli eval --provider fake --json" in failure.command
    assert failure.timeout_seconds == 300
    assert failure.attempts == 2
    assert "\n" not in failure.describe()
    assert failure.describe().startswith("Environment failure: mutation target: command `")


def test_other_errors_are_not_retried_or_hidden() -> None:
    """Only timeouts are environmental; a crash still fails the gate on its first attempt."""
    attempts: list[int] = []

    def measure() -> str:
        attempts.append(1)
        msg = "evaluation crashed"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="evaluation crashed"):
        retry_on_timeout(measure, "mutation target")
    assert attempts == [1]


@pytest.fixture
def green() -> EvalReport:
    """A measured all-green golden report without running the golden subprocess."""
    return EvalReport(
        id="baseline",
        provider="fake",
        suite_digest="fixture",
        created_at=utcnow(),
        passed=1,
        total=1,
        cases=[],
        total_tokens=0,
        total_cost_usd=Decimal(0),
    )


def _catalog() -> tuple[Mutation, ...]:
    return tuple(
        Mutation(name=name, path="guard.py", before="guard", after=name, case=name, runner="pytest")
        for name in ("first", "second")
    )


def _killed(mutation: Mutation) -> MutationResult:
    return MutationResult(
        name=mutation.name,
        killed=True,
        passed=0,
        total=1,
        target=mutation.case,
        runner="pytest",
        failures={mutation.case: ["assertion"]},
    )


def _green_measurement(_node_id: str) -> Measurement:
    return Measurement(exit_code=0, passed=1, total=1, failures={})


def _prepare(monkeypatch: pytest.MonkeyPatch, output: Path, green: EvalReport, *extra: str) -> None:
    monkeypatch.setattr("sys.argv", ["mutate", "--output", str(output), *extra])
    monkeypatch.setattr(mutate, "MUTATIONS", _catalog())
    monkeypatch.setattr(mutate, "test_worker_count", lambda: 2)
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)
    monkeypatch.setattr(mutate, "_evaluate", lambda _directory: (0, green))
    monkeypatch.setattr(mutate, "evaluate_image_baseline", _green_measurement)


def test_main_retry_success_keeps_the_unchanged_success_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, green: EvalReport
) -> None:
    """A single slow attempt is invisible in the verdict once its retry is measured."""
    output = tmp_path / "report.json"
    _prepare(monkeypatch, output, green)
    attempts: list[str] = []

    def run(mutation: Mutation) -> MutationResult:
        attempts.append(mutation.name)
        if attempts.count(mutation.name) == 1 and mutation.name == "second":
            raise _timeout(300)
        return _killed(mutation)

    monkeypatch.setattr(mutate, "run_mutation", run)
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 0
    assert sorted(attempts) == ["first", "second", "second"]
    report = json.loads(output.read_text())
    assert set(report) == {"baseline", "image_baselines", "mutations"}
    assert [item["name"] for item in report["mutations"]] == ["first", "second"]


def test_main_double_timeout_writes_report_names_mutation_and_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    green: EvalReport,
) -> None:
    """Measured mutations stay in the report; the unmeasured one is an environment failure."""
    output = tmp_path / "report.json"
    _prepare(monkeypatch, output, green)

    def run(mutation: Mutation) -> MutationResult:
        if mutation.name == "second":
            raise _timeout(300)
        return _killed(mutation)

    monkeypatch.setattr(mutate, "run_mutation", run)
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 1
    report = json.loads(output.read_text())
    assert [item["name"] for item in report["mutations"]] == ["first"]
    assert [item["target"] for item in report["environment_failures"]] == ["mutation second"]
    lines = capsys.readouterr().out.splitlines()
    failures = [line for line in lines if line.startswith("Environment failure:")]
    assert len(failures) == 1
    assert "mutation second" in failures[0]
    assert "datakeel.cli eval" in failures[0]
    assert "second: ENVIRONMENT FAILURE (timed out twice)" in lines


@pytest.mark.parametrize("phase", ["golden", "pytest"])
def test_main_baseline_double_timeout_writes_report_without_running_mutants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, green: EvalReport, phase: str
) -> None:
    """An unmeasured baseline still blocks every mutant, but leaves a report and no crash."""
    output = tmp_path / "report.json"
    _prepare(monkeypatch, output, green)

    def slow(*_arguments: object) -> object:
        raise _timeout()

    if phase == "golden":
        monkeypatch.setattr(mutate, "_evaluate", slow)
    else:
        monkeypatch.setattr(mutate, "evaluate_image_baseline", _REAL_IMAGE_BASELINE)
        monkeypatch.setattr(mutate, "evaluate_image_test", slow)

    def forbidden(_mutation: Mutation) -> MutationResult:
        pytest.fail("Mutation ran before a measured baseline")

    monkeypatch.setattr(mutate, "run_mutation", forbidden)
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 1
    report = json.loads(output.read_text())
    assert report["mutations"] == []
    targets = [item["target"] for item in report["environment_failures"]]
    if phase == "golden":
        assert report["baseline"] is None
        assert targets == ["golden baseline"]
    else:
        assert report["baseline"]["passed"] == 1
        assert targets == ["pytest baseline first", "pytest baseline second"]


def test_mutate_process_reports_environment_failure_without_a_stack_trace(
    tmp_path: Path,
) -> None:
    """The real script exits nonzero with one plain line per failure and no traceback."""
    driver = tmp_path / "driver.py"
    output = tmp_path / "report.json"
    driver.write_text(
        "import subprocess, sys\n"
        "from scripts import mutate\n"
        "def slow(_directory):\n"
        f"    raise subprocess.TimeoutExpired(cmd={EVAL_COMMAND!r}, timeout=900)\n"
        "mutate._copy_source = lambda _directory: None\n"
        "mutate._evaluate = slow\n"
        f"sys.argv = ['mutate', '--output', {str(output)!r}]\n"
        "mutate.main()\n",
        encoding="utf-8",
    )
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment["PYTHONPATH"] = str(ROOT)
    process = subprocess.run(  # noqa: S603  # Fixed interpreter and generated local driver.
        [sys.executable, str(driver)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = process.stdout + process.stderr
    assert process.returncode == 1, combined
    assert "Traceback" not in combined
    failures = [line for line in process.stdout.splitlines() if "Environment failure" in line]
    expected = (
        "Environment failure: golden baseline: command "
        f"`{shlex.join(EVAL_COMMAND)}` timed out after 900 seconds on all 2 attempts"
    )
    assert failures == [expected]
    assert json.loads(output.read_text())["environment_failures"][0]["target"] == (
        "golden baseline"
    )
