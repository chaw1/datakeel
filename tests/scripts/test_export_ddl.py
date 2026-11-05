# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ensure live DDL differences remain visible beyond a table-name count."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from scripts.export_ddl import DDLSnapshot, snapshot


def _capture(ddl: tuple[str, ...]) -> DDLSnapshot:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            for statement in ddl:
                connection.execute(text(statement))
            return snapshot(connection)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "definition",
    [
        "id INTEGER PRIMARY KEY, value TEXT NOT NULL DEFAULT 'x'",
        "id INTEGER PRIMARY KEY, value TEXT DEFAULT 'y'",
        "id INTEGER PRIMARY KEY, value INTEGER DEFAULT 'x'",
        "id INTEGER PRIMARY KEY, value TEXT DEFAULT 'x' CHECK(value != 'bad')",
        "id INTEGER PRIMARY KEY, value TEXT DEFAULT 'x' UNIQUE",
        "id INTEGER UNIQUE, value TEXT DEFAULT 'x'",
        "id INTEGER PRIMARY KEY, value TEXT DEFAULT 'x' REFERENCES sample(id)",
    ],
)
def test_column_and_constraint_changes_do_not_pass_ddl_oracle(definition: str) -> None:
    """Types, defaults, nullable, PK, FK, unique and check definitions are observable."""
    before = _capture(("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT DEFAULT 'x')",))
    after = _capture((f"CREATE TABLE sample ({definition})",))
    assert before != after


@pytest.mark.parametrize(
    "extra",
    [
        "CREATE INDEX sample_value ON sample(value)",
        "CREATE UNIQUE INDEX sample_value ON sample(value) WHERE value IS NOT NULL",
        "CREATE TRIGGER immutable BEFORE UPDATE ON sample BEGIN SELECT RAISE(ABORT, 'no'); END",
    ],
)
def test_indexes_predicates_and_triggers_are_in_full_snapshot(extra: str) -> None:
    """Identical table sets still fail when secondary DDL changes."""
    table = "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)"
    before = _capture((table,))
    after = _capture((table, extra))
    assert before != after


def test_exporter_does_not_initialize_an_empty_database() -> None:
    """Schema export itself is read-only, even before initialization."""
    empty = _capture(())
    assert empty.dialect == "sqlite"
    assert empty.version
    assert empty.records == ()
