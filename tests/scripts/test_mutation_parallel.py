# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parallel mutation runs retain ordered evidence, source isolation and green baselines."""

from __future__ import annotations

import json
import subprocess
import threading
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import utcnow
from scripts import mutate
from scripts.mutation_models import Mutation, MutationResult
from scripts.mutation_models import TestMeasurement as Measurement
from scripts.mutation_parallel import ordered_parallel_map

if TYPE_CHECKING:
    from pathlib import Path


def test_parallel_results_keep_catalog_order_when_completion_order_differs() -> None:
    """A completed later target cannot reorder the durable catalog evidence."""
    second_finished = threading.Event()
    finished: list[int] = []

    def operation(value: int) -> str:
        if value == 0:
            assert second_finished.wait(timeout=5)
        finished.append(value)
        if value == 1:
            second_finished.set()
        return str(value)

    assert list(ordered_parallel_map(operation, [0, 1], workers=2)) == ["0", "1"]
    assert finished == [1, 0]


def test_parallel_map_with_one_worker_runs_every_item_on_calling_thread() -> None:
    """The documented serial escape hatch adds no thread or omitted work."""
    caller = threading.get_ident()
    observed: list[tuple[int, int]] = []

    def operation(value: int) -> int:
        observed.append((value, threading.get_ident()))
        return value

    assert list(ordered_parallel_map(operation, [0, 1, 2], workers=1)) == [0, 1, 2]
    assert observed == [(0, caller), (1, caller), (2, caller)]


def test_parallel_worker_error_propagates_instead_of_becoming_a_kill() -> None:
    """A crashed evaluation fails the gate instead of entering the success report."""

    def operation(value: int) -> int:
        if value == 1:
            msg = "evaluation crashed"
            raise RuntimeError(msg)
        return value

    with pytest.raises(RuntimeError, match="evaluation crashed"):
        list(ordered_parallel_map(operation, [0, 1], workers=2))


def test_concurrent_mutants_use_separate_cleaned_source_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutating the same source path concurrently cannot leak into another run or checkout."""
    source = tmp_path / "source"
    for relative in ("datakeel", "contracts", "docs/p9", "tests"):
        (source / relative).mkdir(parents=True)
    original = source / "datakeel/guard.py"
    original.write_text("guard", encoding="utf-8")
    monkeypatch.setattr(mutate, "ROOT", source)
    ready = threading.Barrier(2)
    directories: list[Path] = []

    def evaluate(directory: Path, node_id: str) -> Measurement:
        directories.append(directory)
        ready.wait(timeout=5)
        assert (directory / "datakeel/guard.py").read_text() == node_id
        assert original.read_text() == "guard"
        return Measurement(exit_code=1, passed=0, total=1, failures={node_id: ["assertion"]})

    monkeypatch.setattr(mutate, "evaluate_image_test", evaluate)
    mutations = [
        Mutation(
            name=value, path="guard.py", before="guard", after=value, case=value, runner="pytest"
        )
        for value in ("first", "second")
    ]
    results = list(ordered_parallel_map(mutate.run_mutation, mutations, workers=2))
    assert [result.name for result in results] == ["first", "second"]
    assert all(result.killed for result in results)
    assert len(set(directories)) == 2
    assert all(not directory.exists() for directory in directories)
    assert original.read_text() == "guard"


@pytest.fixture
def golden_baseline() -> EvalReport:
    """Provide a measured all-green report without running the golden subprocess."""
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


def _mutations() -> tuple[Mutation, ...]:
    return tuple(
        Mutation(
            name=value, path="guard.py", before="guard", after=value, case=value, runner="pytest"
        )
        for value in ("first", "second")
    )


@pytest.mark.parametrize("baseline_kind", ["golden", "image"])
def test_red_baseline_blocks_every_mutant_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    golden_baseline: EvalReport,
    baseline_kind: str,
) -> None:
    """Parallel execution may begin only after every declared baseline has passed."""
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["mutate", "--output", str(output)])
    monkeypatch.setattr(mutate, "MUTATIONS", _mutations())
    monkeypatch.setattr(mutate, "test_worker_count", lambda: 2)
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)
    monkeypatch.setattr(
        mutate, "_evaluate", lambda _directory: (int(baseline_kind == "golden"), golden_baseline)
    )
    monkeypatch.setattr(
        mutate,
        "evaluate_image_baseline",
        lambda _node_id: Measurement(
            exit_code=1, passed=0, total=1, failures={"first": ["assertion"]}
        ),
    )

    def forbidden(_mutation: Mutation) -> MutationResult:
        pytest.fail("Mutation ran before a green baseline")

    monkeypatch.setattr(mutate, "run_mutation", forbidden)
    with pytest.raises(RuntimeError, match=f"{baseline_kind.title()} baseline"):
        mutate.main()
    assert not output.exists()


def test_main_waits_for_all_baselines_and_writes_catalog_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    golden_baseline: EvalReport,
) -> None:
    """All targets run once and successful evidence preserves the existing report schema."""
    output = tmp_path / "report.json"
    baselines: list[str] = []
    monkeypatch.setattr("sys.argv", ["mutate", "--output", str(output)])
    monkeypatch.setattr(mutate, "MUTATIONS", _mutations())
    monkeypatch.setattr(mutate, "test_worker_count", lambda: 2)
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)
    monkeypatch.setattr(mutate, "_evaluate", lambda _directory: (0, golden_baseline))

    def baseline(node_id: str) -> Measurement:
        baselines.append(node_id)
        return Measurement(exit_code=0, passed=1, total=1, failures={})

    def run(mutation: Mutation) -> MutationResult:
        assert set(baselines) == {"first", "second"}
        return MutationResult(
            name=mutation.name,
            killed=True,
            passed=0,
            total=1,
            target=mutation.case,
            runner="pytest",
            failures={mutation.case: ["assertion"]},
        )

    monkeypatch.setattr(mutate, "evaluate_image_baseline", baseline)
    monkeypatch.setattr(mutate, "run_mutation", run)
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 0
    report = json.loads(output.read_text())
    assert set(report) == {"baseline", "image_baselines", "mutations"}
    assert [item["name"] for item in report["mutations"]] == ["first", "second"]
    assert len(report["image_baselines"]) == 2


def test_main_worker_timeout_fails_without_publishing_a_success_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, golden_baseline: EvalReport
) -> None:
    """A subprocess timeout after green baselines cannot become successful mutation evidence."""
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["mutate", "--output", str(output)])
    monkeypatch.setattr(mutate, "MUTATIONS", _mutations())
    monkeypatch.setattr(mutate, "test_worker_count", lambda: 2)
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)
    monkeypatch.setattr(mutate, "_evaluate", lambda _directory: (0, golden_baseline))
    monkeypatch.setattr(
        mutate,
        "evaluate_image_baseline",
        lambda _node_id: Measurement(exit_code=0, passed=1, total=1, failures={}),
    )

    attempts: list[str] = []

    def timeout(mutation: Mutation) -> MutationResult:
        attempts.append(mutation.name)
        raise subprocess.TimeoutExpired(cmd="synthetic-target", timeout=300)

    monkeypatch.setattr(mutate, "run_mutation", timeout)
    # SPEED-2: a timeout is retried once, then reported as an environment failure.
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 1
    assert sorted(attempts) == ["first", "first", "second", "second"]
    report = json.loads(output.read_text())
    assert report["mutations"] == []
    assert [item["target"] for item in report["environment_failures"]] == [
        "mutation first",
        "mutation second",
    ]


def test_image_baselines_get_separate_cleaned_source_copies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent pytest baselines cannot overwrite each other's fixed JUnit filename."""
    ready = threading.Barrier(2)
    directories: list[Path] = []
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)

    def evaluate(directory: Path, node_id: str) -> Measurement:
        directories.append(directory)
        report = directory / "test-results.xml"
        report.write_text(node_id, encoding="utf-8")
        ready.wait(timeout=5)
        assert report.read_text() == node_id
        return Measurement(exit_code=0, passed=1, total=1, failures={})

    monkeypatch.setattr(mutate, "evaluate_image_test", evaluate)
    results = list(
        ordered_parallel_map(mutate.evaluate_image_baseline, ["first", "second"], workers=2)
    )
    assert len(results) == 2
    assert len(set(directories)) == 2
    assert all(not directory.exists() for directory in directories)


def test_pytest_mutant_disables_nested_workers_and_inherited_scheduling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only outer mutation workers consume the configured process budget."""
    monkeypatch.setenv("DATAKEEL_TEST_WORKERS", "16")
    target = "tests/test_target.py::target"

    def process(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[command.index("-n") + 1] == "0"
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert "DATAKEEL_TEST_WORKERS" not in environment
        (tmp_path / "test-results.xml").write_text(
            '<testsuites><testsuite><testcase name="target" classname="tests.test_target"/>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(mutate.subprocess, "run", process)
    assert mutate.evaluate_image_test(tmp_path, target).passed == 1
