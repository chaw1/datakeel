# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Only real sandbox cases share a worker; ordinary cases remain individually schedulable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from scripts import pytest_groups

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _Item:
    nodeid: str
    markers: list[pytest.MarkDecorator] = field(default_factory=list)

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        """Record added marks without replacing or reordering existing ones."""
        self.markers.append(marker)


def test_collection_marks_only_the_exact_security_file_without_reordering() -> None:
    """Similar filenames and neighboring directories cannot accidentally share affinity."""
    security = [
        _Item(pytest_groups.SECURITY_NODE_PREFIX + f"test_generated[{number}]")
        for number in range(29)
    ]
    others = [
        _Item(node_id)
        for node_id in (
            "tests/operators/custom_sandbox/test_security.py",
            "tests/operators/custom_sandbox/test_security.py_extra::test_case",
            "tests/operators/custom_sandbox/test_security_extra.py::test_case",
            "other/tests/operators/custom_sandbox/test_security.py::test_case",
            "tests/operators/custom_sandbox/test_runtime.py::test_case",
            "tests/core/test_security.py::test_case",
        )
    ]
    items = [*security[:10], *others, *security[10:]]
    original = tuple(items)
    node_ids = [item.nodeid for item in items]
    pytest_groups.pytest_collection_modifyitems(cast("list[pytest.Item]", items))
    assert tuple(items) == original
    assert [item.nodeid for item in items] == node_ids
    assert all(
        [(marker.name, marker.kwargs) for marker in item.markers]
        == [("xdist_group", {"name": pytest_groups.SECURITY_GROUP})]
        for item in security
    )
    assert all(not item.markers for item in others)


def test_collection_keeps_existing_marks_and_selection_metadata() -> None:
    """Grouping does not replace integration, skip or other pre-existing decisions."""
    existing = pytest.mark.integration
    target = _Item(pytest_groups.SECURITY_NODE_PREFIX + "test_generated", [existing])
    ordinary = _Item("tests/core/test_generated.py::test_case", [existing])
    pytest_groups.pytest_collection_modifyitems(cast("list[pytest.Item]", [target, ordinary]))
    assert target.markers[0] is existing
    assert ordinary.markers == [existing]
    assert len(target.markers) == 2


def _run_pytest(
    project: Path, arguments: list[str], report: Path
) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_", "COV_CORE_"))
        and key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "COVERAGE_PROCESS_START"}
    }
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join((str(ROOT), str(project), str(report.parent))),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "SPEED1_GROUP_REPORT": str(report),
        }
    )
    return subprocess.run(  # noqa: S603  # Fixed pytest executable and generated local test paths.
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
        timeout=60,
        check=False,
    )


def test_real_security_collection_groups_29_cases_without_changing_selection(
    tmp_path: Path,
) -> None:
    """The repository's actual security cases get affinity while collection stays identical."""
    (tmp_path / "group_audit.py").write_text(
        "import json, os\nfrom pathlib import Path\n"
        "def pytest_collection_finish(session):\n"
        "    rows = [{'nodeid': item.nodeid, 'groups': [marker.kwargs.get('name') "
        "for marker in item.iter_markers('xdist_group')]} for item in session.items]\n"
        "    Path(os.environ['SPEED1_GROUP_REPORT']).write_text(json.dumps(rows))\n",
        encoding="utf-8",
    )
    arguments = [
        "-p",
        "group_audit",
        "--collect-only",
        "-q",
        "-n",
        "0",
        "tests/operators/custom_sandbox/test_security.py",
        "tests/core/test_errors.py",
    ]
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before = _run_pytest(ROOT, arguments, before_path)
    assert before.returncode == 0, before.stdout + before.stderr
    after = _run_pytest(ROOT, ["-p", "scripts.pytest_groups", *arguments], after_path)
    assert after.returncode == 0, after.stdout + after.stderr
    original = json.loads(before_path.read_text())
    grouped = json.loads(after_path.read_text())
    assert [item["nodeid"] for item in grouped] == [item["nodeid"] for item in original]
    assert all(not item["groups"] for item in original)
    security = [
        item for item in grouped if item["nodeid"].startswith(pytest_groups.SECURITY_NODE_PREFIX)
    ]
    assert len(security) == 29
    assert all(item["groups"] == [pytest_groups.SECURITY_GROUP] for item in security)
    assert all(
        not item["groups"]
        for item in grouped
        if not item["nodeid"].startswith(pytest_groups.SECURITY_NODE_PREFIX)
    )


def _write_synthetic_project(tmp_path: Path) -> Path:
    security = tmp_path / "tests/operators/custom_sandbox/test_security.py"
    security.parent.mkdir(parents=True)
    normal = tmp_path / "tests/test_normal.py"
    results = tmp_path / "results"
    results.mkdir()
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import json, os\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.fixture(scope='session')\n"
        "def sandbox_instance(worker_id):\n"
        "    root = Path(os.environ['SPEED1_GROUP_REPORT'])\n"
        "    (root / ('fixture-' + worker_id)).write_text(worker_id)\n"
        "    return worker_id\n",
        encoding="utf-8",
    )
    security.write_text(
        "import json, os\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.mark.parametrize('number', range(29))\n"
        "def test_security(number, sandbox_instance, worker_id):\n"
        "    root = Path(os.environ['SPEED1_GROUP_REPORT'])\n"
        "    (root / f'security-{number}.json').write_text(json.dumps(worker_id))\n"
        "    assert sandbox_instance == worker_id\n",
        encoding="utf-8",
    )
    normal.write_text(
        "import json, os, time\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.mark.parametrize('number', range(8))\n"
        "def test_normal(number, worker_id):\n"
        "    root = Path(os.environ['SPEED1_GROUP_REPORT'])\n"
        "    (root / f'normal-{number}.json').write_text(json.dumps(worker_id))\n"
        "    (root / ('ready-' + worker_id)).touch()\n"
        "    deadline = time.monotonic() + 20\n"
        "    while len(list(root.glob('ready-*'))) < 2:\n"
        "        assert time.monotonic() < deadline, 'ordinary cases did not span workers'\n"
        "        time.sleep(0.01)\n",
        encoding="utf-8",
    )
    return results


def test_loadgroup_keeps_security_on_one_worker_and_splits_ordinary_cases(tmp_path: Path) -> None:
    """Real xdist workers prove hook order, one fixture construction and per-case dispatch."""
    results = _write_synthetic_project(tmp_path)
    process = _run_pytest(
        tmp_path, ["-p", "scripts.pytest_groups", "-n", "2", "--dist=loadgroup", "-q"], results
    )
    assert process.returncode == 0, process.stdout + process.stderr
    security_results = [json.loads(path.read_text()) for path in results.glob("security-*.json")]
    ordinary_results = [json.loads(path.read_text()) for path in results.glob("normal-*.json")]
    assert len(security_results) == 29
    assert len(set(security_results)) == 1
    assert len(list(results.glob("fixture-*"))) == 1
    assert len(ordinary_results) == 8
    assert set(ordinary_results) == {"gw0", "gw1"}
