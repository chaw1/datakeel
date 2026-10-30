# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Split one complete collection into whole-module shards and record per-test evidence."""

from __future__ import annotations

import heapq
import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import Field

from scripts.shard_spec import ShardModel, ShardSpec, parse_shard

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DURATIONS_PATH = Path(__file__).with_name("pytest_durations.json")
SELECTION_FILE = "selection.json"
OUTCOMES_FILE = "outcomes.json"
_FAILED = ("failed", "error")


class ShardSelection(ShardModel):
    """The complete collection seen by one process and the node IDs it kept.

    IDs are the plain collection IDs; ``reported_as`` maps the IDs that test reports carry
    when pytest-xdist's loadgroup appended an ``@group`` suffix back to the plain ones.
    """

    shard: ShardSpec | None
    collected: tuple[str, ...]
    selected: tuple[str, ...]
    reported_as: dict[str, str] = Field(default_factory=dict)


class ShardOutcomes(ShardModel):
    """Final outcome and summed phase seconds for every reported node ID."""

    outcomes: dict[str, str]
    durations: dict[str, float]


def module_of(nodeid: str) -> str:
    """Return the test file that owns a node ID; a whole file always stays in one shard."""
    return nodeid.split("::", 1)[0]


def plain_nodeid(item: pytest.Item) -> str:
    """Drop the exact ``@group`` suffix loadgroup appends on workers to grouped tests."""
    names = {
        str(mark.args[0] if mark.args else mark.kwargs.get("name", "default"))
        for mark in item.iter_markers("xdist_group")
    }
    suffix = "@" + "_".join(sorted(names))
    if names and item.nodeid.endswith(suffix):
        return item.nodeid.removesuffix(suffix)
    return item.nodeid


def load_durations(path: Path = DURATIONS_PATH) -> dict[str, float]:
    """Read measured seconds per test module, or nothing when no measurement is committed."""
    if not path.is_file():
        return {}
    measured = json.loads(path.read_text(encoding="utf-8"))
    return {str(module): float(seconds) for module, seconds in measured.items()}


def plan_shards(
    nodeids: Sequence[str], count: int, durations: Mapping[str, float]
) -> dict[str, int]:
    """Assign every module to exactly one shard with longest-processing-time-first packing.

    Unmeasured modules weigh their test count times the measured mean seconds per test, so
    a new file still lands somewhere and the plan stays deterministic for every process.
    """
    tests = Counter(module_of(nodeid) for nodeid in nodeids)
    known = [module for module in tests if module in durations]
    known_tests = sum(tests[module] for module in known)
    per_test = sum(durations[module] for module in known) / known_tests if known_tests else 1.0
    weights = {module: durations.get(module, tests[module] * per_test) for module in tests}
    loads = [(0.0, index) for index in range(1, count + 1)]
    plan: dict[str, int] = {}
    for module in sorted(tests, key=lambda name: (-weights[name], name)):
        load, index = heapq.heappop(loads)
        plan[module] = index
        heapq.heappush(loads, (load + weights[module], index))
    return plan


def _writes_selection(config: pytest.Config) -> bool:
    worker = getattr(config, "workerinput", None)
    return worker is None or worker.get("workerid") == "gw0"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Declare the shard selector and the evidence directory."""
    group = parser.getgroup("datakeel shards")
    group.addoption("--shard", default=None, help="Run whole-module shard K of N, written K/N.")
    group.addoption(
        "--shard-report", default=None, help="Directory for selection and outcome evidence."
    )


def pytest_configure(config: pytest.Config) -> None:
    """Record outcomes where reports arrive: the controller, or the only process."""
    report = config.getoption("shard_report")
    if report is not None and not hasattr(config, "workerinput"):
        config.pluginmanager.register(OutcomeRecorder(Path(report)), "datakeel-shard-outcomes")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep this shard's modules after every other selection, preserving item order."""
    value = config.getoption("shard")
    try:
        spec = None if value is None else parse_shard(value)
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    plain = {item.nodeid: plain_nodeid(item) for item in items}
    collected = tuple(plain[item.nodeid] for item in items)
    if spec is not None:
        plan = plan_shards(collected, spec.count, load_durations())
        kept = [item for item in items if plan[module_of(item.nodeid)] == spec.index]
        dropped = [item for item in items if plan[module_of(item.nodeid)] != spec.index]
        if dropped:
            config.hook.pytest_deselected(items=dropped)
        items[:] = kept
    report = config.getoption("shard_report")
    if report is not None and _writes_selection(config):
        directory = Path(report)
        directory.mkdir(parents=True, exist_ok=True)
        selection = ShardSelection(
            shard=spec,
            collected=collected,
            selected=tuple(plain[item.nodeid] for item in items),
            reported_as={
                item.nodeid: plain[item.nodeid]
                for item in items
                if item.nodeid != plain[item.nodeid]
            },
        )
        (directory / SELECTION_FILE).write_text(selection.model_dump_json(), encoding="utf-8")


class OutcomeRecorder:
    """Fold setup, call and teardown reports into one outcome per node ID."""

    def __init__(self, directory: Path) -> None:
        """Accumulate in memory and write once when the session finishes."""
        self.directory = directory
        self.outcomes: dict[str, str] = {}
        self.durations: dict[str, float] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """A failure in any phase wins; a skip wins over a pass; passing needs the call."""
        nodeid = report.nodeid
        self.durations[nodeid] = self.durations.get(nodeid, 0.0) + report.duration
        previous = self.outcomes.get(nodeid)
        if previous in _FAILED:
            return
        if report.failed:
            self.outcomes[nodeid] = "failed" if report.when == "call" else "error"
        elif hasattr(report, "wasxfail"):
            self.outcomes[nodeid] = "xfailed" if report.skipped else "xpassed"
        elif report.skipped:
            self.outcomes[nodeid] = "skipped"
        elif report.when == "call" and previous is None:
            self.outcomes[nodeid] = "passed"

    def pytest_sessionfinish(self) -> None:
        """Write the outcome evidence even when tests failed, for the completeness check."""
        self.directory.mkdir(parents=True, exist_ok=True)
        evidence = ShardOutcomes(outcomes=self.outcomes, durations=self.durations)
        (self.directory / OUTCOMES_FILE).write_text(evidence.model_dump_json(), encoding="utf-8")
