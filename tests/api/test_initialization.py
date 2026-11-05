# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application construction migrates by default and reuses explicitly prepared stores."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text

from datakeel.api.app import create_app
from datakeel.core.errors import ValidationError
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from datakeel.core.schema import CanonicalSchema, SchemaContribution


@pytest.mark.parametrize("explicit", [False, True])
def test_create_app_migrates_by_default_or_when_explicitly_enabled(
    unmigrated_db: Database, monkeypatch: pytest.MonkeyPatch, *, explicit: bool
) -> None:
    """Both enabled forms pass the complete persistence inputs to a real migration."""
    attempted: list[Database] = []
    original = Database.migrate

    def record(
        database: Database,
        contributions: tuple[SchemaContribution, ...],
        *,
        canonical: CanonicalSchema,
    ) -> None:
        attempted.append(database)
        assert contributions == schema_contributions()
        assert canonical == canonical_schema()
        original(database, contributions, canonical=canonical)

    monkeypatch.setattr(Database, "migrate", record)
    assert inspect(unmigrated_db.engine).get_table_names() == []
    app = create_app(unmigrated_db, run_migrations=True) if explicit else create_app(unmigrated_db)
    assert attempted == [unmigrated_db]
    assert app.state.db is unmigrated_db
    assert set(inspect(unmigrated_db.engine).get_table_names()) == {
        item.table for item in canonical_schema().tables
    }


def test_create_app_when_migrations_disabled_reuses_prepared_database(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit opt-out never migrates or removes an initialized benchmark fact table."""
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE scale_facts (value INTEGER)"))
        connection.execute(text("INSERT INTO scale_facts VALUES (7)"))

    def fail(
        database: Database,
        contributions: tuple[SchemaContribution, ...],
        *,
        canonical: CanonicalSchema,
    ) -> None:
        pytest.fail("Application construction must reuse the prepared database without migration")

    monkeypatch.setattr(Database, "migrate", fail)
    app = create_app(db, run_migrations=False)
    assert app.state.db is db
    with db.engine.connect() as connection:
        assert connection.scalar(text("SELECT value FROM scale_facts")) == 7
    assert set(inspect(db.engine).get_table_names()) == {
        *(item.table for item in canonical_schema().tables),
        "scale_facts",
    }


def test_create_app_default_still_rejects_benchmark_table(db: Database) -> None:
    """The benchmark opt-out cannot weaken the default canonical table validation."""
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE scale_facts (value INTEGER)"))
    with pytest.raises(ValidationError, match=r"Canonical tables mismatch.*scale_facts"):
        create_app(db)
