# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Source mutations must invalidate a persisted prefix before any pending upgrade."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from datakeel.core.settings import Settings
from datakeel.versioning.campaign import status, upgrade
from datakeel.versioning.registry import registry
path, home = Path(sys.argv[2]), Path(sys.argv[3])
first = registry()[0]
second = first.model_copy(update=dict(version=2, checksum='2'*64,
    source=first.target.id, forward=lambda connection: None))
versions = (first, second)
if sys.argv[4] == 'seed':
    report = upgrade(path, Settings(home=home), versions, to=1)
elif sys.argv[4] == 'status':
    report = status(path, home, versions)
else:
    report = upgrade(path, Settings(home=home), versions)
print(json.dumps(dict(checksum=first.checksum, registrations=len(registry()),
    report=report.model_dump(mode='json'))))
"""


def _probe(source: Path, home: Path, action: str) -> dict[str, object]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("DATAKEEL_")
    }
    result = subprocess.run(  # noqa: S603  # Fixed local probe and generated fixture paths.
        [
            sys.executable,
            "-I",
            "-c",
            _PROBE,
            str(source),
            str(home / "db.sqlite"),
            str(home),
            action,
        ],
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _facts(home: Path) -> tuple[object, ...]:
    with sqlite3.connect(home / "db.sqlite") as connection:
        return (
            connection.execute(
                "SELECT * FROM datakeel_schema_versions ORDER BY version"
            ).fetchall(),
            connection.execute("SELECT * FROM file_discovery_checkpoints").fetchall(),
        )


@pytest.mark.parametrize(
    ("filename", "original", "mutated"),
    [
        ("inspect.py", '"PRAGMA foreign_key_check"', '"SELECT 1 WHERE 0"'),
        (
            "inspect.py",
            'return {"sqlite_blob_hex": value.hex()}',
            'return {"sqlite_blob_hex_changed": value.hex()}',
        ),
        (
            "campaign.py",
            "if existed and definition.preserve_facts and before != after:",
            "if False and existed and definition.preserve_facts and before != after:",
        ),
    ],
    ids=["baseline-helper", "fact-fingerprint-helper", "campaign-postcondition"],
)
def test_helper_source_drift_refuses_status_and_pending_upgrade_until_restored(
    tmp_path: Path, filename: str, original: str, mutated: str
) -> None:
    """Independent source edits cannot re-sign an existing ledger or execute its next version."""
    source = tmp_path / "source"
    shutil.copytree(
        Path("datakeel"),
        source / "datakeel",
        ignore=shutil.ignore_patterns("__pycache__", "web_dist"),
    )
    home = tmp_path / "home"
    control = _probe(source, home, "seed")
    assert control["report"]["exit_code"] == 0
    before = _facts(home)
    packages = tuple(sorted((home / "backups").rglob("*")))
    database_bytes = (home / "db.sqlite").read_bytes()
    path = source / "datakeel" / "versioning" / filename
    contents = path.read_text()
    assert contents.count(original) == 1
    path.write_text(contents.replace(original, mutated))
    try:
        for action in ("status", "upgrade"):
            result = _probe(source, home, action)
            assert result["checksum"] != control["checksum"], "W4-helper-checksum-drift"
            assert result["report"]["exit_code"] == 3, "W4-helper-checksum-rejected"
            assert "checksum" in result["report"]["error"].lower()
            assert _facts(home) == before, "W4-helper-no-ledger-or-fact-writes"
            assert (home / "db.sqlite").read_bytes() == database_bytes
            assert tuple(sorted((home / "backups").rglob("*"))) == packages
    finally:
        path.write_text(contents)
    restored = _probe(source, home, "status")
    assert restored["checksum"] == control["checksum"]
    assert restored["report"]["state"] == "pending"
    resumed = _probe(source, home, "upgrade")
    assert resumed["report"]["exit_code"] == 0
    assert resumed["report"]["applied"] == [2]
    after = _facts(home)
    assert after[0][0] == before[0][0]
    assert after[1] == before[1]


def test_v1_closure_covers_transitive_local_helpers_and_explicit_policies() -> None:
    """Audit dependencies independently of the forward handler and the checksum calculator."""
    import ast  # noqa: PLC0415

    from datakeel.versioning.registry import registry  # noqa: PLC0415

    definition = registry()[0]
    expected = {
        "core/catalog_identity.py",
        "core/errors.py",
        "core/models.py",
        "core/orchestration.py",
        "core/recovery.py",
        "core/routing_models.py",
        "core/settings.py",
        "routing/models.py",
        "versioning/campaign.py",
        "versioning/configuration.py",
        "versioning/inspect.py",
        "versioning/location.py",
        "versioning/lock.py",
        "versioning/models.py",
        "versioning/recovery.py",
        "versioning/recovery_models.py",
        "versioning/references.py",
        "versioning/sqlite_b1.json",
        "versioning/v1.py",
    }
    assert set(definition.checksum_sources) == expected
    assert definition.preserve_facts is True
    assert {"preserve_facts", "minimum_reader", "source", "target"} <= definition.model_fields_set
    for name in expected - {"versioning/sqlite_b1.json"}:
        for node in ast.walk(ast.parse((Path("datakeel") / name).read_text())):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("datakeel.")
            ):
                dependency = node.module.removeprefix("datakeel.").replace(".", "/") + ".py"
                assert dependency in expected, (name, dependency)


def test_future_registration_does_not_change_v1_checksum(tmp_path: Path) -> None:
    """Appending a real registry entry and a future source file leaves the v1 prefix valid."""
    source = tmp_path / "source"
    shutil.copytree(
        Path("datakeel"),
        source / "datakeel",
        ignore=shutil.ignore_patterns("__pycache__", "web_dist"),
    )
    home = tmp_path / "home"
    before = _probe(source, home, "seed")
    path = source / "datakeel" / "versioning" / "registry.py"
    contents = path.read_text()
    path.write_text(
        contents.replace(
            "return (definition(), vector_definition(), rank_definition())",
            (
                "return (definition(), vector_definition(), rank_definition(), "
                "rank_definition().model_copy(update={'version': 4}))"
            ),
        )
    )
    (path.parent / "v4.py").write_text('"""Future migration, outside the v1 closure."""\n')
    after = _probe(source, home, "status")
    assert after["registrations"] == 4
    assert before["checksum"] == after["checksum"]
    assert after["report"]["state"] == "pending"
