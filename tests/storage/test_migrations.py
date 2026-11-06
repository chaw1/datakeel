# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict product recognition is separate from the low-level nullable-column helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from datakeel.core.errors import ValidationError
from datakeel.persistence import migrate
from datakeel.storage import migrations

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.mark.parametrize("extra", [False, True])
def test_partial_tasks_baseline_rejected_without_creating_latest_tables(
    unmigrated_db: Database, *, extra: bool
) -> None:
    """A partial former additive fixture can no longer bypass complete baseline recognition."""
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)")
        if extra:
            connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN legacy_note VARCHAR(40)")
    with pytest.raises(ValidationError):
        migrate(unmigrated_db)
    assert inspect(unmigrated_db.engine).get_table_names() == ["tasks"]


def test_nullable_helper_preserves_extra_columns_types_and_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper's narrow additive behavior remains testable without a production bypass."""
    metadata = MetaData()
    Table("sample", metadata, Column("id", Integer, primary_key=True), Column("note", String))
    monkeypatch.setattr(migrations.Base, "metadata", metadata)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE sample (id INTEGER PRIMARY KEY, extra VARCHAR(40))"
        )
        connection.exec_driver_sql("INSERT INTO sample VALUES (1, 'preserved')")
        migrations.add_nullable_columns(connection)
        migrations.add_nullable_columns(connection)
        assert connection.exec_driver_sql("SELECT * FROM sample").fetchall() == [
            (1, "preserved", None)
        ]
        columns = inspect(connection).get_columns("sample")
        assert str(columns[1]["type"]) == "VARCHAR(40)"
        assert columns[2]["nullable"]
    engine.dispose()


def test_nullable_helper_refuses_to_infer_required_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing mandatory values fail before any nullable column is added."""
    metadata = MetaData()
    Table(
        "sample",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("note", String),
        Column("state", String, nullable=False),
    )
    monkeypatch.setattr(migrations.Base, "metadata", metadata)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        with pytest.raises(ValidationError, match=r"non-nullable column sample.state"):
            migrations.add_nullable_columns(connection)
        assert len(inspect(connection).get_columns("sample")) == 1
    engine.dispose()
