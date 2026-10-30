# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CI shards keep whole modules, cover the full collection once and record real outcomes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_pytest_shards, pytest_durations
from scripts.pytest_shards import (
    OUTCOMES_FILE,
    SELECTION_FILE,
    ShardOutcomes,
    ShardSelection,
    plan_shards,
)
from scripts.shard_spec import ShardSpec, parse_shard

ROOT = Path(__file__).resolve().parents[2]
NODES = tuple(
    f"tests/test_{module}.py::test_{case}"
    for module in "abcdefg"
    for case in range(len(module) + 3)
)


@pytest.mark.parametrize("count", [1, 2, 3, 4, 7, 9])
def test_plan_assigns_every_module_to_exactly_one_existing_shard(count: int) -> None:
    """Whole modules are the unit, so every node follows its file into one shard."""
    plan = plan_shards(NODES, count, {})
    assert set(plan) == {node.split("::")[0] for node in NODES}
    assert set(plan.values()) <= set(range(1, count + 1))
    assert plan == plan_shards(tuple(reversed(NODES)), count, {})


def test_plan_separates_measured_heavy_modules_before_filling_light_ones() -> None:
    """Longest-first packing keeps the two slowest files apart and balances the rest."""
    nodes = [f"tests/test_{name}.py::test_case" for name in ("slow", "slower", "a", "b", "c")]
    durations = {"tests/test_slow.py": 90.0, "tests/test_slower.py": 100.0}
    durations |= {f"tests/test_{n}.py": 10.0 for n in "abc"}
    plan = plan_shards(nodes, 2, durations)
    assert plan["tests/test_slow.py"] != plan["tests/test_slower.py"]
    loads = dict.fromkeys((1, 2), 0.0)
    for module, shard in plan.items():
        loads[shard] += durations[module]
    assert max(loads.values()) - min(loads.values()) <= 10.0


def test_plan_weighs_unmeasured_modules_by_tests_and_measured_mean() -> None:
    """A new file with many tests weighs like many average tests, not like zero."""
    nodes = [
        *(f"tests/test_new.py::test_{index}" for index in range(10)),
        "tests/test_known.py::test_case",
        "tests/test_small.py::test_case",
    ]
    plan = plan_shards(nodes, 2, {"tests/test_known.py": 5.0})
    assert plan["tests/test_new.py"] != plan["tests/test_known.py"]
    assert plan["tests/test_small.py"] == plan["tests/test_known.py"]


@pytest.mark.parametrize("value", ["", "4", "0/4", "5/4", "a/4", "1/b", "-1/4", "1/0"])
def test_malformed_or_out_of_range_shards_are_rejected(value: str) -> None:
    """A typo can never silently select nothing or a shard that does not exist."""
    with pytest.raises(ValueError, match="shard"):
        parse_shard(value)


def _selection(
    index: int | None, collected: tuple[str, ...], selected: tuple[str, ...]
) -> ShardSelection:
    shard = None if index is None else ShardSpec(index=index, count=2)
    return ShardSelection(shard=shard, collected=collected, selected=selected)


def _outcomes(selected: tuple[str, ...], outcome: str = "passed") -> ShardOutcomes:
    return ShardOutcomes(
        outcomes=dict.fromkeys(selected, outcome), durations=dict.fromkeys(selected, 0.1)
    )


def _complete() -> tuple[ShardSelection, list[tuple[ShardSelection, ShardOutcomes | None]]]:
    first = tuple(node for node in NODES if node.startswith(("tests/test_a", "tests/test_b")))
    second = tuple(node for node in NODES if node not in first)
    full = _selection(None, NODES, NODES)
    return full, [
        (_selection(1, NODES, first), _outcomes(first)),
        (_selection(2, NODES, second), _outcomes(second)),
    ]


def test_complete_duplicate_free_shards_pass_the_check() -> None:
    """The union of two disjoint shards equals the full collection."""
    full, shards = _complete()
    assert check_pytest_shards.verify(full, shards, 2) == []


def test_a_test_left_out_of_every_shard_is_reported() -> None:
    """Deliberately dropping one collected test from its shard fails the completeness check."""
    full, shards = _complete()
    (selection, outcomes), other = shards
    dropped = selection.selected[0]
    kept = selection.selected[1:]
    tampered = (selection.model_copy(update={"selected": kept}), outcomes)
    problems = check_pytest_shards.verify(full, [tampered, other], 2)
    assert any("ran in no shard" in problem and dropped in problem for problem in problems)


def test_a_test_in_two_shards_and_split_module_are_reported() -> None:
    """Running one test twice is also an error; it would hide a missing one in the count."""
    full, shards = _complete()
    (first, first_outcomes), (second, second_outcomes) = shards
    duplicate = second.selected[0]
    tampered = first.model_copy(update={"selected": (*first.selected, duplicate)})
    problems = check_pytest_shards.verify(
        full, [(tampered, first_outcomes), (second, second_outcomes)], 2
    )
    assert any("more than one shard" in problem for problem in problems)
    assert any("split across shards" in problem for problem in problems)


def test_missing_shard_foreign_plan_or_different_collection_is_reported() -> None:
    """Every shard must exist once, use the same plan size and see the same collection."""
    full, shards = _complete()
    first, second = shards
    assert any("expected shards 1..2" in p for p in check_pytest_shards.verify(full, [first], 2))
    other_size = (first[0].model_copy(update={"shard": ShardSpec(index=1, count=3)}), first[1])
    assert any(
        "planned for 3" in p for p in check_pytest_shards.verify(full, [other_size, second], 2)
    )
    shrunk = (first[0].model_copy(update={"collected": NODES[1:]}), first[1])
    assert any(
        "different suite" in p for p in check_pytest_shards.verify(full, [shrunk, second], 2)
    )


@pytest.mark.parametrize("outcome", ["failed", "error", "xpassed"])
def test_unreported_or_unsuccessful_outcomes_are_reported(outcome: str) -> None:
    """Selection alone is not evidence: each selected test must pass or skip."""
    full, shards = _complete()
    first, (second, _) = shards
    lost = (second, None)
    assert any("no outcome" in p for p in check_pytest_shards.verify(full, [first, lost], 2))
    bad = (second, _outcomes(second.selected, outcome))
    assert any(
        "did not pass or skip" in p for p in check_pytest_shards.verify(full, [first, bad], 2)
    )
    partial = (second, _outcomes(second.selected[1:]))
    assert any("never reported" in p for p in check_pytest_shards.verify(full, [first, partial], 2))


def _run(project: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_", "COV_CORE_"))
        and key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "COVERAGE_PROCESS_START"}
    }
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join((str(ROOT), str(project))),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
    )
    return subprocess.run(  # noqa: S603  # Fixed interpreter and generated local test paths.
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "xdist.plugin",
            "-p",
            "no:cacheprovider",
            *arguments,
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _write_project(root: Path) -> None:
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    for name in "abcde":
        (tests / f"test_{name}.py").write_text(
            "import pytest\n"
            "@pytest.mark.parametrize('number', range(3))\n"
            "def test_case(number):\n"
            "    assert number < 3\n"
            "def test_skipped():\n"
            "    pytest.skip('declared skip')\n",
            encoding="utf-8",
        )


def test_real_xdist_shards_cover_the_collection_once_and_the_cli_agrees(tmp_path: Path) -> None:
    """Three real sharded runs with workers equal one full collection; tampering is caught."""
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    reports = tmp_path / "reports"
    plugin = ["-p", "scripts.pytest_groups", "-p", "scripts.pytest_shards"]
    full = _run(project, [*plugin, "--collect-only", "-q", f"--shard-report={tmp_path / 'full'}"])
    assert full.returncode == 0, full.stdout + full.stderr
    for index in (1, 2, 3):
        process = _run(
            project,
            [
                *plugin,
                "-n",
                "2",
                "--dist=loadgroup",
                f"--shard={index}/3",
                f"--shard-report={reports / f'shard-{index}'}",
            ],
        )
        assert process.returncode == 0, process.stdout + process.stderr
    arguments = ["--collection", str(tmp_path / "full"), "--shards", str(reports), "--count", "3"]
    checked = _check(arguments)
    assert checked.returncode == 0, checked.stdout
    assert "collected 20; passed 15; skipped 5" in checked.stdout
    target = reports / "shard-2" / SELECTION_FILE
    selection = json.loads(target.read_text())
    selection["selected"] = selection["selected"][1:]
    target.write_text(json.dumps(selection))
    tampered = _check(arguments)
    assert tampered.returncode == 1
    assert "ran in no shard" in tampered.stdout


def _check(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # Fixed module and generated local evidence paths.
        [sys.executable, "-m", "scripts.check_pytest_shards", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_outcomes_fold_every_phase_into_one_result(tmp_path: Path) -> None:
    """Setup errors, failures, skips and expected failures keep distinct final outcomes."""
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (project / "tests/test_mixed.py").write_text(
        "import pytest\n"
        "@pytest.fixture\ndef broken():\n    raise RuntimeError('setup')\n"
        "def test_pass():\n    pass\n"
        "def test_fail():\n    assert False\n"
        "def test_error(broken):\n    pass\n"
        "def test_skip():\n    pytest.skip('skip')\n"
        "@pytest.mark.xfail(strict=False)\ndef test_xfail():\n    assert False\n",
        encoding="utf-8",
    )
    report = tmp_path / "report"
    process = _run(project, ["-p", "scripts.pytest_shards", f"--shard-report={report}"])
    assert process.returncode == 1
    outcomes = ShardOutcomes.model_validate_json((report / OUTCOMES_FILE).read_text()).outcomes
    assert {node.split("::")[1]: outcome for node, outcome in outcomes.items()} == {
        "test_pass": "passed",
        "test_fail": "failed",
        "test_error": "error",
        "test_skip": "skipped",
        "test_xfail": "xfailed",
    }


def test_invalid_shard_option_is_a_usage_error(tmp_path: Path) -> None:
    """Pytest stops with a usage error instead of collecting an arbitrary subset."""
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    process = _run(project, ["-p", "scripts.pytest_shards", "--shard=4/3"])
    assert process.returncode == pytest.ExitCode.USAGE_ERROR
    assert "shard index must be between 1 and N" in process.stderr


def test_plugin_loads_without_importing_datakeel_before_coverage_starts() -> None:
    """``-p`` plugins import before pytest-cov measures, so the plugin must not pull datakeel.

    The first sharded CI run lost 49 covered lines of ``datakeel/__init__.py`` and
    ``datakeel/core/models.py`` because the plugin imported ``BoundaryModel`` too early.
    """
    probe = (
        "import sys\n"
        "import scripts.pytest_shards\n"
        "print(sorted(name for name in sys.modules if name.split('.')[0] == 'datakeel'))\n"
    )
    process = subprocess.run(  # noqa: S603  # Fixed interpreter and fixed probe source.
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    assert process.stdout.strip() == "[]"


def test_durations_keep_the_slowest_stack_per_module(tmp_path: Path) -> None:
    """Refreshed weights come from measured outcome files, summed per module."""
    for stack, seconds in (("sqlite", 1.0), ("postgres", 2.5)):
        directory = tmp_path / stack / "shard-1"
        directory.mkdir(parents=True)
        evidence = ShardOutcomes(
            outcomes={"tests/test_a.py::one": "passed", "tests/test_a.py::two": "passed"},
            durations={"tests/test_a.py::one": seconds, "tests/test_a.py::two": seconds},
        )
        (directory / OUTCOMES_FILE).write_text(evidence.model_dump_json())
    assert pytest_durations.module_durations([tmp_path]) == {"tests/test_a.py": 5.0}
