# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation shards partition the catalog, and only their complete union can pass the gate."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import utcnow
from scripts import merge_mutation_reports, mutate
from scripts.merge_mutation_reports import ShardReport, judge
from scripts.mutation_models import Mutation, MutationResult
from scripts.mutation_models import TestMeasurement as Measurement
from scripts.mutation_shards import select_mutations
from scripts.mutation_timeouts import EnvironmentFailure
from scripts.shard_spec import ShardSpec

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_real_catalog_shards_are_an_ordered_partition(count: int) -> None:
    """Every catalog mutation lands in exactly one shard, keeping catalog order inside it."""
    shards = [
        select_mutations(mutate.MUTATIONS, ShardSpec(index=i, count=count))
        for i in range(1, count + 1)
    ]
    names = [mutation.name for shard in shards for mutation in shard]
    assert Counter(names) == Counter(mutation.name for mutation in mutate.MUTATIONS)
    order = {mutation.name: position for position, mutation in enumerate(mutate.MUTATIONS)}
    for shard in shards:
        positions = [order[mutation.name] for mutation in shard]
        assert positions == sorted(positions)
    for runner in ("golden", "pytest"):
        sizes = [sum(mutation.runner == runner for mutation in shard) for shard in shards]
        assert max(sizes) - min(sizes) <= 1


CATALOG = (
    *(
        Mutation(name=f"g{index}", path="guard.py", before="a", after="b", case=f"case-{index}")
        for index in range(3)
    ),
    *(
        Mutation(
            name=f"p{index}",
            path="guard.py",
            before="a",
            after="b",
            case=f"tests/test_x.py::test_{index}",
            runner="pytest",
        )
        for index in range(5)
    ),
)


def _baseline() -> EvalReport:
    return EvalReport(
        id="baseline",
        provider="fake",
        suite_digest="fixture",
        created_at=utcnow(),
        passed=2,
        total=2,
        cases=[],
        total_tokens=0,
        total_cost_usd=Decimal(0),
    )


def _report(index: int, count: int = 2) -> ShardReport:
    selected = select_mutations(CATALOG, ShardSpec(index=index, count=count))
    return ShardReport(
        shard=f"{index}/{count}",
        baseline=_baseline(),
        image_baselines=[
            Measurement(exit_code=0, passed=1, total=1, failures={})
            for mutation in selected
            if mutation.runner == "pytest"
        ],
        mutations=[
            MutationResult(
                name=mutation.name,
                killed=True,
                passed=0,
                total=1,
                runner=mutation.runner,
                target=mutation.case,
            )
            for mutation in selected
        ],
    )


def test_complete_green_shards_pass_the_merged_gate() -> None:
    """Both shards green at baseline and all mutants killed is the original success rule."""
    assert judge([_report(1), _report(2)], 2, CATALOG) == []


def test_missing_shard_or_mutation_fails_the_merged_gate() -> None:
    """A lost shard or a dropped result cannot shrink the catalog that must be killed."""
    assert any("expected shards 1..2" in p for p in judge([_report(1)], 2, CATALOG))
    first = _report(1)
    dropped = first.model_copy(update={"mutations": first.mutations[1:]})
    problems = judge([dropped, _report(2)], 2, CATALOG)
    assert any("measured" in problem for problem in problems)
    assert any("merged reports cover" in problem for problem in problems)


def test_survivor_red_baseline_or_environment_failure_fails_the_merged_gate() -> None:
    """Each original judgment still applies to every shard after the merge."""
    first, second = _report(1), _report(2)
    survivor = first.mutations[0].model_copy(update={"killed": False})
    survived = first.model_copy(update={"mutations": [survivor, *first.mutations[1:]]})
    assert any("survived" in p for p in judge([survived, second], 2, CATALOG))
    red = _baseline().model_copy(update={"passed": 1})
    assert any(
        "golden baseline" in p
        for p in judge([first.model_copy(update={"baseline": red}), second], 2, CATALOG)
    )
    failing = Measurement(exit_code=1, passed=0, total=1, failures={"x": ["assertion"]})
    image = first.model_copy(update={"image_baselines": [failing, *first.image_baselines[1:]]})
    assert any("pytest baselines" in p for p in judge([image, second], 2, CATALOG))
    failure = EnvironmentFailure(target="mutation g0", command="python -m x", timeout_seconds=900)
    timed_out = first.model_copy(update={"environment_failures": [failure]})
    problems = judge([timed_out, second], 2, CATALOG)
    assert any("Environment failure: mutation g0" in problem for problem in problems)


def test_sharded_main_runs_only_its_mutations_and_labels_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shard report says which shard it is and holds exactly that shard's results."""
    output = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", ["mutate", "--shard", "2/2", "--output", str(output)])
    monkeypatch.setattr(mutate, "MUTATIONS", CATALOG)
    monkeypatch.setattr(mutate, "test_worker_count", lambda: 2)
    monkeypatch.setattr(mutate, "_copy_source", lambda _directory: None)
    monkeypatch.setattr(mutate, "_evaluate", lambda _directory: (0, _baseline()))
    baselines: list[str] = []

    def baseline(node_id: str) -> Measurement:
        baselines.append(node_id)
        return Measurement(exit_code=0, passed=1, total=1, failures={})

    monkeypatch.setattr(mutate, "evaluate_image_baseline", baseline)
    monkeypatch.setattr(
        mutate,
        "run_mutation",
        lambda mutation: MutationResult(
            name=mutation.name,
            killed=True,
            passed=0,
            total=1,
            runner=mutation.runner,
            target=mutation.case,
        ),
    )
    with pytest.raises(SystemExit) as exit_info:
        mutate.main()
    assert exit_info.value.code == 0
    report = json.loads(output.read_text())
    assert report["shard"] == "2/2"
    assert [item["name"] for item in report["mutations"]] == ["g1", "p1", "p3"]
    assert sorted(baselines) == ["tests/test_x.py::test_1", "tests/test_x.py::test_3"]
    assert judge([ShardReport.model_validate(report), _report(1)], 2, CATALOG) == []


def test_merge_command_writes_catalog_ordered_report_and_fails_on_a_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CI command prints the merged counts and exits nonzero when a shard is missing."""
    monkeypatch.setattr(merge_mutation_reports, "MUTATIONS", CATALOG)
    paths = []
    for index in (1, 2):
        path = tmp_path / f"mutation-{index}.json"
        path.write_text(_report(index).model_dump_json())
        paths.append(str(path))
    output = tmp_path / "merged.json"
    monkeypatch.setattr("sys.argv", ["merge", "--count", "2", "--output", str(output), *paths])
    with pytest.raises(SystemExit) as exit_info:
        merge_mutation_reports.main()
    assert exit_info.value.code == 0
    assert (
        "measured 8 of 8; killed 8; survived 0; environment failures 0" in capsys.readouterr().out
    )
    merged = json.loads(output.read_text())
    assert [item["name"] for item in merged["mutations"]] == [m.name for m in CATALOG]
    monkeypatch.setattr("sys.argv", ["merge", "--count", "2", paths[0]])
    with pytest.raises(SystemExit) as exit_info:
        merge_mutation_reports.main()
    assert exit_info.value.code == 1
    assert "Mutation gate failed: expected shards 1..2" in capsys.readouterr().out
