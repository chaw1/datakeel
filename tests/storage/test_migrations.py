# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upgrade legacy tables with the same SQLite/PostgreSQL fixture used by CI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text

from datakeel.core.errors import ValidationError
from datakeel.storage.task_queries import list_tasks

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _legacy_tasks(db: Database, *, omit_state: bool = False) -> None:
    state_column = "" if omit_state else "state VARCHAR NOT NULL,"
    with db.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE tasks (id VARCHAR PRIMARY KEY, dataset_id VARCHAR NOT NULL, "
                f"idempotency_key VARCHAR NOT NULL UNIQUE, {state_column}"
                "queue VARCHAR NOT NULL, pipeline JSON, created_at FLOAT NOT NULL, "
                "total_shards INTEGER NOT NULL, error VARCHAR)"
            )
        )
        if not omit_state:
            connection.execute(
                text(
                    "INSERT INTO tasks "
                    "(id, dataset_id, idempotency_key, state, queue, created_at, total_shards) "
                    "VALUES ('legacy-task', 'legacy-dataset', 'legacy-key', "
                    "'COMPLETED', 'cpu', 1700000000, 1)"
                )
            )


def test_migrate_old_task_schema_preserves_data_and_is_idempotent(
    unmigrated_db: Database,
) -> None:
    """Old tasks keep their original values and unknown finish times after repeated upgrades."""
    _legacy_tasks(unmigrated_db)
    before = inspect(unmigrated_db.engine).get_columns("tasks")
    assert "finished_at" not in {column["name"] for column in before}
    unmigrated_db.migrate()
    unmigrated_db.migrate()
    tasks = list_tasks(unmigrated_db)
    assert [(task.id, task.state, task.created_at, task.finished_at) for task in tasks] == [
        ("legacy-task", "COMPLETED", 1700000000, None)
    ]
    columns = {
        column["name"]: column for column in inspect(unmigrated_db.engine).get_columns("tasks")
    }
    assert columns["finished_at"]["nullable"]
    assert columns["input_version_id"]["nullable"]


def test_concurrent_old_schema_migrations_share_the_lock(unmigrated_db: Database) -> None:
    """Concurrent startup callers cannot both try to add the same legacy column."""
    _legacy_tasks(unmigrated_db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: unmigrated_db.migrate(), range(4)))
    assert len(list_tasks(unmigrated_db)) == 1


def test_migrate_missing_required_column_fails_without_guessing_values(
    unmigrated_db: Database,
) -> None:
    """An incompatible old table is rejected with a concrete table and column reason."""
    _legacy_tasks(unmigrated_db, omit_state=True)
    with pytest.raises(ValidationError, match=r"non-nullable column tasks.state.*existing rows"):
        unmigrated_db.migrate()
    columns = {column["name"] for column in inspect(unmigrated_db.engine).get_columns("tasks")}
    assert "finished_at" not in columns
    assert "state" not in columns


def test_migrate_keeps_unknown_columns_and_existing_column_types(unmigrated_db: Database) -> None:
    """Additive upgrades leave extra legacy facts and type declarations untouched."""
    _legacy_tasks(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.execute(text("ALTER TABLE tasks ADD COLUMN legacy_note VARCHAR(40)"))
        connection.execute(text("UPDATE tasks SET legacy_note = 'preserved'"))
    before = inspect(unmigrated_db.engine).get_columns("tasks")
    unmigrated_db.migrate()
    after = inspect(unmigrated_db.engine).get_columns("tasks")
    assert {column["name"]: str(column["type"]) for column in before}.items() <= {
        column["name"]: str(column["type"]) for column in after
    }.items()
    with unmigrated_db.engine.connect() as connection:
        assert connection.scalar(text("SELECT legacy_note FROM tasks")) == "preserved"
