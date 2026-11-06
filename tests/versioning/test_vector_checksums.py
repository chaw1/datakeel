# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""V2 checksum binds its own full execution closure without changing the v1 prefix."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from datakeel.versioning.registry import registry
from tests.versioning.test_vector_v2 import V1_CHECKSUM


def test_v2_closure_contains_every_transitive_local_import() -> None:
    """Audit the complete runner/inspection/recovery/DDL closure independently of the hash code."""
    first, second = registry()
    sources = set(second.checksum_sources)
    assert sources == set(first.checksum_sources) | {
        "versioning/campaign_v2.py",
        "versioning/facts_v2.py",
        "versioning/inspect_v2.py",
        "versioning/sqlite_b2.json",
        "versioning/sqlite_b2_altered_shards.json",
        "versioning/v2.py",
    }
    assert first.checksum == V1_CHECKSUM
    assert second.preserve_facts is True
    for name in sources:
        if not name.endswith(".py"):
            continue
        for node in ast.walk(ast.parse((Path("datakeel") / name).read_text())):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("datakeel.")
            ):
                dependency = node.module.removeprefix("datakeel.").replace(".", "/") + ".py"
                assert dependency in sources, (name, dependency)


_PROBE = """
import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from datakeel.core.settings import Settings
from datakeel.versioning.registry import registry
from datakeel.versioning.campaign_v2 import upgrade, status
source, home, action = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
versions = registry()
report = (upgrade(home/'db', Settings(home=home), versions) if action != 'status'
          else status(home/'db', home, versions))
print(json.dumps(dict(checksums=[v.checksum for v in versions],
                     report=report.model_dump(mode='json'))))
"""


def _probe(source: Path, home: Path, action: str) -> dict[str, object]:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("DATAKEEL_")}
    result = subprocess.run(  # noqa: S603  # Fixed local source probe, no service or network calls.
        [sys.executable, "-I", "-c", _PROBE, str(source), str(home), action],
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("filename", "before", "after"),
    [
        ("facts_v2.py", "if changed:", "if False:"),
        ("inspect_v2.py", '"PRAGMA foreign_key_check"', '"SELECT 1 WHERE 0"'),
        ("v2.py", "ADD COLUMN lease_expires_at FLOAT", "ADD COLUMN lease_expires_at TEXT"),
    ],
)
def test_v2_source_drift_rejects_existing_head_without_resigning_v1(
    tmp_path: Path, filename: str, before: str, after: str
) -> None:
    """Changed v2 helpers cannot execute or re-sign a persisted ledger, even if DDL is unchanged."""
    source, home = tmp_path / "source", tmp_path / "home"
    shutil.copytree(
        Path("datakeel"),
        source / "datakeel",
        ignore=shutil.ignore_patterns("__pycache__", "web_dist"),
    )
    control = _probe(source, home, "seed")
    assert control["report"]["exit_code"] == 0
    database = (home / "db").read_bytes()
    backups = tuple(sorted((home / "backups").rglob("*")))
    path = source / "datakeel" / "versioning" / filename
    contents = path.read_text()
    assert contents.count(before) == 1
    path.write_text(contents.replace(before, after))
    for action in ("status", "upgrade"):
        result = _probe(source, home, action)
        assert result["checksums"][0] == control["checksums"][0] == V1_CHECKSUM
        assert result["checksums"][1] != control["checksums"][1]
        assert result["report"]["exit_code"] == 3, "W4-v2-helper-drift-rejected"
        assert (home / "db").read_bytes() == database
        assert tuple(sorted((home / "backups").rglob("*"))) == backups
    path.write_text(contents)
    assert _probe(source, home, "status")["report"]["state"] == "current"
