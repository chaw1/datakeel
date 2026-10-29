# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exclusive scheduling preserves the collection, idle workers and crash failures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from scripts.pytest_scheduler import ExclusiveSecurityScheduling

if TYPE_CHECKING:
    from xdist.workermanage import WorkerController

ROOT = Path(__file__).resolve().parents[2]
SECURITY = "tests/operators/custom_sandbox/test_security.py::test_case"
GROUP = "@custom-sandbox-security"


@dataclass
class _Gateway:
    id: str


@dataclass(eq=False)
class _Node:
    gateway: _Gateway
    sent: list[list[int]] = field(default_factory=list)
    shutting_down: bool = False
    shutdown_calls: int = 0

    def send_runtest_some(self, indices: list[int]) -> None:
        """Record work assignments without running a worker process."""
        self.sent.append(indices)

    def shutdown(self) -> None:
        """Retain the worker's public shutdown state for scheduler assertions."""
        self.shutting_down = True
        self.shutdown_calls += 1


class _Plugins:
    def register(self, plugin: object, name: str) -> None:
        """Accept the scheduler's lifecycle hook registration."""


class _Hooks:
    def __init__(self) -> None:
        self.reports: list[pytest.CollectReport] = []

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        """Retain explicit crash errors, including crashes of idle workers."""
        self.reports.append(report)


class _Config:
    def __init__(self) -> None:
        self.pluginmanager = _Plugins()
        self.hook = _Hooks()

    def getvalue(self, name: str) -> list[str]:
        """Provide the two local worker specifications consumed by xdist."""
        assert name == "tx"
        return ["popen", "popen"]


def _scheduler(
    collection: list[str],
) -> tuple[ExclusiveSecurityScheduling, list[_Node], _Config]:
    config = _Config()
    scheduler = ExclusiveSecurityScheduling(cast("pytest.Config", config))
    nodes = [_Node(_Gateway("gw0")), _Node(_Gateway("gw1"))]
    for fake in nodes:
        node = cast("WorkerController", fake)
        scheduler.add_node(node)
        scheduler.add_node_collection(node, collection)
    scheduler.schedule()
    return scheduler, nodes, config


def test_security_phase_keeps_idle_worker_and_releases_every_ordinary_item_once() -> None:
    """One ordinary lookahead unblocks the final security protocol without early dispatch."""
    collection = [
        "test_plain.py::a",
        SECURITY + "[0]" + GROUP,
        "test_plain.py::b",
        SECURITY + "[1]" + GROUP,
        "test_plain.py::c",
    ]
    scheduler, nodes, _config = _scheduler(collection)
    assert nodes[0].sent == [[1, 3], [0]]
    assert not nodes[1].sent
    assert not nodes[1].shutting_down
    assert not scheduler.tests_finished
    scheduler.mark_test_complete(cast("WorkerController", nodes[0]), 1)
    assert not nodes[1].sent
    assert not nodes[1].shutting_down
    scheduler.mark_test_complete(cast("WorkerController", nodes[0]), 3)
    assert nodes[1].sent
    assert sorted(index for node in nodes for batch in node.sent for index in batch) == list(
        range(5)
    )


def test_security_only_collection_keeps_idle_worker_until_final_protocol() -> None:
    """A sentinel releases the final security case without prematurely closing other workers."""
    scheduler, nodes, _config = _scheduler([SECURITY + GROUP])
    assert nodes[0].sent == [[0]]
    assert nodes[0].shutting_down
    assert not nodes[1].shutting_down
    assert not scheduler.tests_finished
    scheduler.mark_test_complete(cast("WorkerController", nodes[0]), 0)
    assert scheduler.tests_finished
    assert nodes[1].shutting_down


@pytest.mark.parametrize("crashed", [0, 1])
def test_any_worker_crash_aborts_without_dispatching_more_work(crashed: int) -> None:
    """Both an active security worker and an idle worker failure invalidate the run."""
    scheduler, nodes, config = _scheduler(
        [SECURITY + GROUP, "test_plain.py::a", "test_plain.py::b"]
    )
    sent = [list(node.sent) for node in nodes]
    node = cast("WorkerController", nodes[crashed])
    scheduler.pytest_testnodedown(node, "generated worker crash")
    scheduler.remove_node(node)
    scheduler.schedule()
    assert scheduler.tests_finished
    assert config.hook.reports[0].failed
    assert [entry.sent for entry in nodes] == sent


def test_idle_crash_tracks_healthy_drain_without_requeuing_or_false_crash() -> None:
    """A healthy worker finishes queued protocols after abort and exits normally."""
    scheduler, nodes, config = _scheduler(
        [
            SECURITY + "[0]" + GROUP,
            SECURITY + "[1]" + GROUP,
            "test_plain.py::queued",
            "test_plain.py::unassigned",
        ]
    )
    healthy = cast("WorkerController", nodes[0])
    idle = cast("WorkerController", nodes[1])
    sent = [list(node.sent) for node in nodes]
    scheduler.pytest_testnodedown(idle, "generated idle worker crash")
    assert scheduler.remove_node(idle) is None
    scheduler.schedule()
    for index in (0, 1, 2):
        scheduler.mark_test_complete(healthy, index)
    scheduler.pytest_testnodedown(healthy, None)
    assert scheduler.remove_node(healthy) is None
    assert len(config.hook.reports) == 1
    assert config.hook.reports[0].failed
    assert [node.sent for node in nodes] == sent
    assert nodes[0].shutdown_calls == 1
    assert scheduler.tests_finished


def _project(path: Path, security_count: int, ordinary_count: int, *, crash: bool = False) -> Path:
    results = path / "results"
    results.mkdir()
    (path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (path / "scheduler_plugin.py").write_text(
        "import pytest\nfrom scripts.pytest_scheduler import ExclusiveSecurityScheduling\n"
        "@pytest.hookimpl(tryfirst=True)\n"
        "def pytest_xdist_make_scheduler(config, log):\n"
        "    return ExclusiveSecurityScheduling(config, log)\n",
        encoding="utf-8",
    )
    (path / "conftest.py").write_text(
        "import json, os\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.fixture(scope='module')\n"
        "def security_instance(worker_id):\n"
        "    root = Path(os.environ['SPEED1_SCHEDULER_RESULTS'])\n"
        "    (root / ('fixture-' + worker_id)).touch()\n"
        "    yield\n"
        "    (root / ('cleanup-' + worker_id)).touch()\n"
        "@pytest.fixture\n"
        "def security_case(number, worker_id, security_instance):\n"
        "    root = Path(os.environ['SPEED1_SCHEDULER_RESULTS'])\n"
        "    assert not list(root.glob('ordinary-*'))\n"
        "    yield\n"
        "    assert not list(root.glob('ordinary-*'))\n"
        "    (root / f'security-{number}').write_text(json.dumps(worker_id))\n",
        encoding="utf-8",
    )
    security = path / "tests/operators/custom_sandbox/test_security.py"
    security.parent.mkdir(parents=True)
    if security_count:
        security.write_text(
            "import os\nimport pytest\n"
            f"@pytest.mark.parametrize('number', range({security_count}))\n"
            "def test_security(number, security_case):\n"
            f"    if {crash!r} and number == 0:\n        os._exit(17)\n",
            encoding="utf-8",
        )
    if ordinary_count:
        _write_ordinary(path, security_count, ordinary_count)
    return results


def _write_ordinary(path: Path, security_count: int, count: int) -> None:
    (path / "tests/test_ordinary.py").write_text(
        "import json, os, time\nfrom pathlib import Path\nimport pytest\n"
        f"@pytest.mark.parametrize('number', range({count}))\n"
        "def test_ordinary(number, worker_id):\n"
        "    root = Path(os.environ['SPEED1_SCHEDULER_RESULTS'])\n"
        f"    assert len(list(root.glob('security-*'))) == {security_count}\n"
        f"    assert len(list(root.glob('cleanup-*'))) == {int(bool(security_count))}\n"
        "    (root / f'ordinary-{number}').write_text(json.dumps(worker_id))\n"
        "    (root / ('ready-' + worker_id)).touch()\n"
        "    deadline = time.monotonic() + 45\n"
        "    while len(list(root.glob('ready-*'))) < 2:\n"
        "        assert time.monotonic() < deadline, 'ordinary phase did not use both workers'\n"
        "        time.sleep(0.01)\n",
        encoding="utf-8",
    )


def _run(project: Path, results: Path) -> subprocess.CompletedProcess[str]:
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
            "SPEED1_SCHEDULER_RESULTS": str(results),
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "xdist.plugin",
            "-p",
            "scripts.pytest_groups",
            "-p",
            "scheduler_plugin",
            "-p",
            "no:cacheprovider",
            "-n",
            "2",
            "--dist=loadgroup",
            "-q",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def test_real_workers_run_security_exclusively_then_all_ordinary_cases(tmp_path: Path) -> None:
    """Each security teardown ends before ordinary setup; the next phase retains both workers."""
    results = _project(tmp_path, 29, 8)
    process = _run(tmp_path, results)
    assert process.returncode == 0, process.stdout + process.stderr
    security = [json.loads(path.read_text()) for path in results.glob("security-*")]
    ordinary = [json.loads(path.read_text()) for path in results.glob("ordinary-*")]
    assert len(security) == 29
    assert len(set(security)) == 1
    assert len(list(results.glob("fixture-*"))) == 1
    assert len(list(results.glob("cleanup-*"))) == 1
    assert len(ordinary) == 8
    assert set(ordinary) == {"gw0", "gw1"}


def test_real_security_only_collection_finishes_without_idle_worker_deadlock(
    tmp_path: Path,
) -> None:
    """No ordinary lookahead is necessary when a shutdown sentinel is supplied."""
    results = _project(tmp_path, 3, 0)
    process = _run(tmp_path, results)
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(list(results.glob("security-*"))) == 3


def test_real_ordinary_only_collection_still_runs_every_item_in_parallel(tmp_path: Path) -> None:
    """Collections that omit the security file retain ordinary loadgroup behavior."""
    results = _project(tmp_path, 0, 8)
    process = _run(tmp_path, results)
    assert process.returncode == 0, process.stdout + process.stderr
    ordinary = [json.loads(path.read_text()) for path in results.glob("ordinary-*")]
    assert len(ordinary) == 8
    assert set(ordinary) == {"gw0", "gw1"}


def test_real_security_worker_crash_fails_without_running_ordinary_cases(tmp_path: Path) -> None:
    """A replacement worker must not turn an interrupted exclusive phase into a green gate."""
    results = _project(tmp_path, 3, 8, crash=True)
    process = _run(tmp_path, results)
    assert process.returncode != 0
    assert "Worker crashed during isolated scheduling" in process.stdout + process.stderr
    assert not list(results.glob("ordinary-*"))
