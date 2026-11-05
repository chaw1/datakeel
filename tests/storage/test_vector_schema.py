# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent two-dialect DDL oracle and non-destructive SQLite lease upgrades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from datakeel.core.errors import ValidationError
from datakeel.core.schema import Base, validate_contributions
from datakeel.persistence import migrate
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import Dialect

    from datakeel.storage.database import Database

ORACLE = Path("contracts/persistence/we-e2-ddl.json")


def _compiled(dialect: Dialect) -> dict[str, dict[str, str | list[str]]]:
    return {
        table.name: {
            "table": str(CreateTable(table).compile(dialect=dialect)).strip(),
            "indexes": sorted(
                str(CreateIndex(index).compile(dialect=dialect)).strip() for index in table.indexes
            ),
        }
        for table in Base.metadata.sorted_tables
    }


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()], ids=["sqlite", "pg"])
def test_ddl_preserves_every_main_table_except_explicit_vector_and_lease_additions(
    dialect: Dialect,
) -> None:
    """Every column, constraint and index matches the frozen main plus the exact increment."""
    oracle = json.loads(ORACLE.read_text())
    expected = {**oracle["baseline"][dialect.name], **oracle["increment"][dialect.name]}
    assert _compiled(dialect) == expected


def test_nullable_lease_upgrade_preserves_existing_shard_and_is_idempotent(
    unmigrated_db: Database,
) -> None:
    """An actual pre-E2 SQLite database gains three tables and a null lease without data loss."""
    if not unmigrated_db.sqlite:
        pytest.skip("SQLite baseline DDL; the PG oracle above compiles without a connection")
    baseline = json.loads(ORACLE.read_text())["baseline"]["sqlite"]
    with unmigrated_db.engine.begin() as connection:
        for ddl in baseline.values():
            connection.exec_driver_sql(ddl["table"])
            for index in ddl["indexes"]:
                connection.exec_driver_sql(index)
        connection.execute(
            text("INSERT INTO datasets VALUES ('d', 'fixture', 0, '[]', '{}', NULL, '{}', '{}')")
        )
        connection.execute(
            text(
                "INSERT INTO tasks (id, dataset_id, idempotency_key, state, queue, created_at, "
                "total_shards) VALUES ('t', 'd', 'key', 'QUEUED', 'cpu', 0, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO task_shards (id, task_id, ordinal, state, inputs, outputs, attempts) "
                "VALUES ('s', 't', 0, 'QUEUED', '[]', '[]', 0)"
            )
        )
    migrate(unmigrated_db)
    migrate(unmigrated_db)
    with unmigrated_db.engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, task_id, lease_expires_at FROM task_shards")
        ).one() == ("s", "t", None)
        assert len(inspect(connection).get_table_names()) == 102


@pytest.mark.parametrize("defect", ["omitted", "wrong-owner"])
def test_vector_contribution_cannot_be_omitted_or_reassigned(defect: str) -> None:
    """The separate vector inventory enforces its owner even when metadata is loaded."""
    contributions = schema_contributions()
    if defect == "omitted":
        changed = contributions[:-1]
    else:
        changed = (
            *contributions[:-1],
            contributions[-1].model_copy(update={"owner": "worker_store"}),
        )
    with pytest.raises(ValidationError):
        validate_contributions(changed, canonical_schema())


def test_vector_contribution_has_independent_canonical_owner() -> None:
    """All three vector tables belong to the separately declared inventory owner."""
    vector = schema_contributions()[-1]
    expected = {item.table for item in canonical_schema().tables if item.owner == "vector_store"}
    assert vector.owner == "vector_store"
    assert {row.__tablename__ for row in vector.rows} == expected
    assert len(expected) == 3
