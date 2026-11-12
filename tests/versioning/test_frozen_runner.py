# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The frozen v2 runner still campaigns its own prefix after later registrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.storage.database import Database
from datakeel.versioning.campaign_v2 import status, upgrade, validate_registry
from datakeel.versioning.inspect import facts_digest
from datakeel.versioning.inspect_v2 import LEDGER_TRIGGERS
from datakeel.versioning.registry import registry
from tests.versioning.test_baselines import legacy
from tests.versioning.test_vector_v2 import _seed

if TYPE_CHECKING:
    from datakeel.storage.database import Database as DatabaseType

VERSIONS = registry()[:2]


def test_registry_order_and_chain_are_validated_before_writes() -> None:
    """Duplicated, unordered or broken-chain registrations cannot start a campaign."""
    with pytest.raises(ValidationError, match="registry order"):
        validate_registry((VERSIONS[0], VERSIONS[0]))
    with pytest.raises(ValidationError, match="baseline chain"):
        validate_registry((VERSIONS[0], VERSIONS[0].model_copy(update={"version": 2})))


def test_status_missing_isolated_and_unknown_target_are_classified(tmp_path: Path) -> None:
    """Missing files, recovery isolation and unknown targets keep their stable exits."""
    home = tmp_path / "home"
    assert status(home / "absent", home, VERSIONS).state == "missing"
    home.mkdir()
    (home / "recovery-isolation.json").write_text("{}")
    report = status(home / "absent", home, VERSIONS)
    assert (report.state, report.exit_code) == ("isolated", 6)
    assert upgrade(home / "db", Settings(home=home), VERSIONS, to=99).exit_code == 2


def test_s3_recovery_is_refused_before_any_local_write(tmp_path: Path) -> None:
    """The SQLite campaign never probes object storage for a pending upgrade."""
    home = tmp_path / "home"
    result = upgrade(home / "db", Settings(home=home, s3_bucket="generated-fixture"), VERSIONS)
    assert (result.exit_code, result.state) == (4, "missing")
    assert not (home / "db").exists()


def test_v2_runner_upgrades_empty_store_and_repeats_without_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen runner initializes its own two-version prefix and stays idempotent."""
    home, path = tmp_path / "home", tmp_path / "db.sqlite"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    database = Database(f"sqlite:///{path}")
    result = upgrade(path, Settings(home=home), VERSIONS)
    assert (result.exit_code, result.state, result.applied) == (0, "current", (1, 2))
    repeat = upgrade(path, Settings(home=home), VERSIONS)
    assert (repeat.applied, repeat.backup_manifest) == ((), None)
    assert status(path, home, VERSIONS).state == "current"
    database.engine.dispose()


def test_v2_runner_stamps_unversioned_baseline_preserving_facts(
    unmigrated_db: DatabaseType, tmp_path: Path
) -> None:
    """A complete unversioned v2 store is stamped without DDL replay or fact changes."""
    path = legacy(unmigrated_db, version=2)
    _seed(unmigrated_db, tmp_path, vector=True)
    with unmigrated_db.engine.connect() as connection:
        before = facts_digest(connection)
    result = upgrade(path, Settings(home=tmp_path), VERSIONS)
    assert (result.exit_code, result.applied) == (0, (1, 2))
    with unmigrated_db.engine.connect() as connection:
        assert facts_digest(connection) == before


def test_v2_runner_refuses_downgrade_from_its_own_head(
    unmigrated_db: DatabaseType, tmp_path: Path
) -> None:
    """Requesting an earlier target on a current v2 store is a refused downgrade."""
    path = legacy(unmigrated_db, version=2)
    settings = Settings(home=tmp_path)
    assert upgrade(path, settings, VERSIONS).exit_code == 0
    assert upgrade(path, settings, VERSIONS, to=1).exit_code == 2


def test_v2_runner_retry_rejects_changed_facts_before_handler(
    unmigrated_db: DatabaseType, tmp_path: Path
) -> None:
    """A valid v1 prefix does not authorize reusing its recovery point after writes."""
    path = legacy(unmigrated_db, version=1)
    settings = Settings(home=tmp_path)
    _seed(unmigrated_db, tmp_path)
    assert upgrade(path, settings, VERSIONS, to=1).exit_code == 0
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE datasets SET name='unrelated'")
    result = upgrade(path, settings, VERSIONS)
    assert (result.exit_code, result.version) == (4, 1)


def test_v2_runner_supplied_manifest_from_other_source_is_refused(
    unmigrated_db: DatabaseType, tmp_path: Path
) -> None:
    """A recovery package bound to another database identity cannot back this campaign."""
    path = legacy(unmigrated_db, version=1)
    settings = Settings(home=tmp_path)
    assert upgrade(path, settings, VERSIONS, to=1).exit_code == 0
    other = tmp_path / "other.sqlite"
    other_db = Database(f"sqlite:///{other}")
    legacy(other_db, version=1)
    second = upgrade(other, Settings(home=tmp_path / "other-home"), VERSIONS, to=1)
    assert second.exit_code == 0
    assert second.backup_manifest is not None
    result = upgrade(path, settings, VERSIONS, manifest=Path(second.backup_manifest))
    assert result.exit_code == 4
    other_db.engine.dispose()


@pytest.mark.parametrize("damage", ["fk", "invariant", "ledger"])
def test_v2_recognition_rejects_damaged_facts_and_ledger(
    unmigrated_db: DatabaseType, tmp_path: Path, damage: str
) -> None:
    """FK violations, broken business invariants and forged ledger rows fail closed."""
    path = legacy(unmigrated_db, version=2)
    settings = Settings(home=tmp_path)
    _seed(unmigrated_db, tmp_path, vector=True)
    assert upgrade(path, settings, VERSIONS).exit_code == 0
    if damage == "fk":
        # SQLite ignores PRAGMA foreign_keys inside a transaction; use a raw connection.
        with sqlite3.connect(path) as raw:
            raw.execute(
                "INSERT INTO task_shards "
                "(id,task_id,ordinal,state,inputs,outputs,attempts) "
                "VALUES ('x','missing',0,'QUEUED','[]','[]',0)"
            )
    else:
        with unmigrated_db.engine.begin() as connection:
            if damage == "invariant":
                connection.exec_driver_sql(
                    "INSERT INTO tasks "
                    "(id,dataset_id,idempotency_key,state,queue,created_at,total_shards) "
                    "VALUES ('bad','d','k','BOGUS','cpu',0,0)"
                )
            else:
                connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_update")
                connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_delete")
                connection.exec_driver_sql(
                    "UPDATE datakeel_schema_versions SET checksum='bad' WHERE version=1"
                )
                for sql in LEDGER_TRIGGERS:
                    connection.exec_driver_sql(sql)
    report = status(path, settings.home, VERSIONS)
    assert (report.state, report.exit_code) == ("invalid", 3)


def test_v2_recognition_rejects_unknown_schema(unmigrated_db: DatabaseType, tmp_path: Path) -> None:
    """An extra column outside every frozen form is never implicitly admitted."""
    path = legacy(unmigrated_db, version=2)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE datasets ADD COLUMN extra TEXT")
    report = status(path, tmp_path, VERSIONS)
    assert (report.state, report.exit_code) == ("invalid", 3)
