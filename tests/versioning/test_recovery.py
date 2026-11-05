# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actual WAL snapshots, exhaustive object copies, integrity failures and isolated restores."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import create_engine

from datakeel.core.errors import ValidationError
from datakeel.core.recovery import ISOLATION_MARKER
from datakeel.core.settings import Settings
from datakeel.storage.dq_jobs import schedule_due
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.versioning.campaign import upgrade
from datakeel.versioning.recovery import restore_package, verify_package
from datakeel.versioning.registry import registry
from datakeel.worker.dq_webhooks import relay_webhooks
from datakeel.worker.runner import run_worker
from tests.versioning.helpers import seed_toy, toy_registry
from tests.versioning.test_baselines import legacy

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_wal_snapshot_copies_all_nested_and_column_objects_and_nonsecret_config(
    unmigrated_db: Database, tmp_path: Path
) -> None:
    """A live idle WAL connection's committed rows and every referenced object are restorable."""
    home = tmp_path / "source"
    (home / "objects" / "nested").mkdir(parents=True)
    for key in ("nested/one", "two", "three"):
        (home / "objects" / key).write_bytes(key.encode())
    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datasets VALUES ('ds','WAL fact',1,?, '{}', NULL, '{}','{}')",
            (
                json.dumps(
                    [{"metadata": {"object_key": "nested/one"}, "history": [{"object_key": "two"}]}]
                ),
            ),
        )
        connection.exec_driver_sql("INSERT INTO versions VALUES ('v1','ds',1,'[]',NULL)")
        connection.exec_driver_sql(
            "INSERT INTO training_governance_runs "
            "VALUES ('selection','ds','v1',1,'{}','[]','[]','three')"
        )
    settings = Settings(home=home, openai_api_key="fixture-secret", log_level="DEBUG")
    result = upgrade(path, settings, registry())
    assert result.exit_code == 0, result
    assert result.backup_manifest
    from pathlib import Path  # noqa: PLC0415

    manifest_path = Path(result.backup_manifest)
    manifest = verify_package(manifest_path)
    assert {item.path for item in manifest.objects} == {
        "objects/nested/one",
        "objects/two",
        "objects/three",
    }
    config = (manifest_path.parent / "config.json").read_text()
    assert '"log_level": "DEBUG"' in config
    assert "fixture-secret" not in config + manifest_path.read_text()
    assert "openai_api_key" in manifest.credential_references
    restored = restore_package(manifest_path, tmp_path / "restored")
    engine = create_engine(f"sqlite:///{restored}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT name FROM datasets").scalar() == "WAL fact"
    engine.dispose()
    assert (restored.parent / ISOLATION_MARKER).is_file()
    assert (restored.parent / "objects/nested/one").read_bytes() == b"nested/one"


@pytest.mark.parametrize("damage", ["missing", "hash", "omit-reference", "config", "snapshot"])
def test_incomplete_package_stops_restore_before_destination_exists(
    unmigrated_db: Database, tmp_path: Path, damage: str
) -> None:
    """Missing files, changed bytes and a truncated object inventory are all rejected."""
    home = tmp_path / "source"
    (home / "objects").mkdir(parents=True)
    (home / "objects" / "object").write_bytes(b"reference")
    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datasets VALUES ('ds','ds',1,?, '{}', NULL, '{}','{}')",
            ('[{"object_key":"object"}]',),
        )
    result = upgrade(path, Settings(home=home), registry())
    assert result.backup_manifest
    from pathlib import Path  # noqa: PLC0415

    manifest_path = Path(result.backup_manifest)
    root = manifest_path.parent
    if damage == "missing":
        (root / "objects/object").unlink()
    elif damage == "hash":
        (root / "objects/object").write_bytes(b"bad")
    elif damage == "config":
        (root / "config.json").write_text("{}")
    elif damage == "snapshot":
        (root / "database.sqlite").write_bytes(b"bad")
    else:
        document = json.loads(manifest_path.read_text())
        document["objects"] = []
        manifest_path.write_text(json.dumps(document))
    with pytest.raises((OSError, ValidationError)):
        restore_package(manifest_path, tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_missing_referenced_object_prevents_any_ledger_or_ddl(
    unmigrated_db: Database, tmp_path: Path
) -> None:
    """An absent local object cannot be treated as a complete cache or ignored."""
    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datasets VALUES ('ds','ds',1,?, '{}', NULL, '{}','{}')",
            ('[{"object_key":"missing"}]',),
        )
    result = upgrade(path, Settings(home=tmp_path), registry())
    assert result.exit_code == 4
    assert result.applied == ()
    assert result.version == 0


def test_corrupt_reused_package_prevents_valid_prefix_from_advancing(tmp_path: Path) -> None:
    """A retry must reverify its original recovery point before executing remaining handlers."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    result = upgrade(path, Settings(home=home), toy_registry("data"))
    assert result.exit_code == 5
    assert result.backup_manifest
    from pathlib import Path  # noqa: PLC0415

    (Path(result.backup_manifest).parent / "config.json").write_text("bad")
    failed = upgrade(path, Settings(home=home), toy_registry())
    assert failed.exit_code == 4
    assert failed.version == 1
    assert len(list((home / "backups").iterdir())) == 1


def test_isolation_blocks_actual_worker_scheduler_queue_and_webhook_with_fake_transport(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct scheduler/relay calls also refuse while the marker stays continuously present."""
    from datakeel.core.settings import get_settings  # noqa: PLC0415

    home = get_settings().home
    home.mkdir(parents=True, exist_ok=True)
    marker = home / ISOLATION_MARKER
    marker.write_text("{}")
    sent: list[httpx.Request] = []
    settings = Settings(
        home=home,
        dq_webhook_url="https://webhook.example.test",
        dq_webhook_secret="fixture",  # noqa: S106  # Generated test secret.
    )
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    calls = (
        lambda: run_worker(db, once=True),
        lambda: schedule_due(db),
        lambda: DatabaseQueue(db),
        lambda: relay_webhooks(
            db,
            settings,
            transport=httpx.MockTransport(
                lambda request: sent.append(request) or httpx.Response(200)
            ),
        ),
    )
    for call in calls:
        with pytest.raises(ValidationError, match="Recovery isolation"):
            call()
        assert marker.is_file()
    assert sent == []
