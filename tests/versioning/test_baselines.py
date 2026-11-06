# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Full current-schema equivalence and conservative structural/data/ledger rejection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect

from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.versioning.campaign_v2 import status, upgrade, validate_registry
from datakeel.versioning.inspect import LEDGER
from datakeel.versioning.registry import registry

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def legacy(db: Database, *, version: int = 2) -> Path:
    """Construct the latest baseline independently, or the explicitly frozen v1 fixture."""
    from pathlib import Path  # noqa: PLC0415

    if version == 1:
        from datakeel.versioning.v1 import initial  # noqa: PLC0415

        with db.engine.begin() as connection:
            initial(connection)
    else:
        db.migrate(schema_contributions(), canonical=canonical_schema())
    return Path(str(db.engine.url.database))


@pytest.mark.parametrize("variant", ["empty", "one", "different"])
def test_semantic_baseline_equivalent_data_keeps_unknown_release(
    unmigrated_db: Database, variant: str, tmp_path: Path
) -> None:
    """Schema identity is invariant under empty/different legal business facts."""
    from datakeel.core.settings import Settings  # noqa: PLC0415

    path = legacy(unmigrated_db)
    if variant != "empty":
        with unmigrated_db.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO datasets VALUES (?, ?, 1, '[]', '{}', NULL, '{}', '{}')",
                (variant, variant),
            )
    before = status(path, tmp_path, registry())
    assert (before.state, before.baseline, before.release_source) == (
        "unversioned",
        "sqlite-b2",
        "unknown",
    )
    result = upgrade(path, Settings(home=tmp_path), registry())
    assert (result.exit_code, result.state, result.applied) == (0, "current", (1, 2))
    assert len(inspect(unmigrated_db.engine).get_table_names()) == 103
    assert LEDGER in inspect(unmigrated_db.engine).get_table_names()
    repeat = upgrade(path, Settings(home=tmp_path), registry())
    assert repeat.applied == ()
    assert repeat.backup_manifest is None
    assert len(list((tmp_path / "backups").iterdir())) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE tasks",
        "CREATE TABLE unknown (id INTEGER)",
        "CREATE TABLE sqliteevil (id INTEGER)",
        "ALTER TABLE tasks ADD COLUMN extra TEXT",
        "DROP INDEX ix_tasks_dataset_id",
        "DROP TRIGGER lineage_no_update",
        "INSERT INTO datasets VALUES ('bad','bad',1,'broken','{}',NULL,'{}','{}')",
        "INSERT INTO datasets VALUES ('bad','bad',1,'{}','{}',NULL,'{}','{}')",
    ],
)
def test_unknown_mixed_or_illegal_baseline_fails_closed(
    unmigrated_db: Database, tmp_path: Path, sql: str
) -> None:
    """No latest create_all/installer runs before strict recognition rejects a candidate."""
    from datakeel.core.settings import Settings  # noqa: PLC0415

    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(sql)
    before = path.read_bytes()
    report = upgrade(path, Settings(home=tmp_path), registry())
    assert report.exit_code == 3
    assert path.read_bytes() == before
    assert not (tmp_path / "backups").exists()


def test_reader_threshold_and_unknown_version_are_separate(
    unmigrated_db: Database, tmp_path: Path
) -> None:
    """Reader below/equal/above a known minimum and schema ahead all fail or pass explicitly."""
    from datakeel.core.settings import Settings  # noqa: PLC0415

    path = legacy(unmigrated_db, version=1)
    versions = (registry()[0].model_copy(update={"minimum_reader": 2}),)
    assert upgrade(path, Settings(home=tmp_path), versions).exit_code == 6
    assert status(path, tmp_path, versions, reader=1).state == "ahead"
    assert status(path, tmp_path, versions, reader=2).state == "current"
    assert status(path, tmp_path, versions, reader=3).state == "current"
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datakeel_schema_versions SELECT 2, checksum, baseline, minimum_reader, "
            "applied_at, campaign, facts FROM datakeel_schema_versions"
        )
    assert status(path, tmp_path, versions, reader=100).exit_code == 6


@pytest.mark.parametrize(
    "mutation", ["checksum", "gap", "empty", "schema", "trigger", "timestamp", "facts"]
)
def test_corrupt_ledger_rejected_without_repair(
    unmigrated_db: Database, tmp_path: Path, mutation: str
) -> None:
    """Malformed, missing and forged ledger facts never fall back to legacy stamping."""
    from datakeel.core.settings import Settings  # noqa: PLC0415

    path = legacy(unmigrated_db)
    assert upgrade(path, Settings(home=tmp_path), registry()).exit_code == 0
    with unmigrated_db.engine.begin() as connection:
        if mutation in {"checksum", "gap", "empty", "timestamp", "facts"}:
            connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_update")
            connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_delete")
            if mutation == "empty":
                connection.exec_driver_sql("DELETE FROM datakeel_schema_versions")
            else:
                field = {
                    "checksum": "checksum='bad'",
                    "gap": "version=3",
                    "timestamp": "applied_at='not-a-time'",
                    "facts": "facts='not-a-digest'",
                }[mutation]
                connection.exec_driver_sql(
                    f"UPDATE datakeel_schema_versions SET {field} WHERE version=1"  # noqa: S608  # Fixed fixtures.
                )
            from datakeel.versioning.inspect import LEDGER_TRIGGERS  # noqa: PLC0415

            for sql in LEDGER_TRIGGERS:
                connection.exec_driver_sql(sql)
        elif mutation == "schema":
            connection.exec_driver_sql(f"ALTER TABLE {LEDGER} ADD COLUMN extra TEXT")
        else:
            connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_update")
    assert upgrade(path, Settings(home=tmp_path), registry()).exit_code == 3


def test_registry_requires_contiguous_order() -> None:
    """A duplicated, reversed or missing registration cannot execute."""
    from datakeel.core.errors import ValidationError  # noqa: PLC0415

    with pytest.raises(ValidationError, match="registry order"):
        validate_registry((registry()[0], registry()[0]))
