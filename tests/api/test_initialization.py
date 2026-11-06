# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Backend-specific startup and explicit reuse of caller-initialized databases."""

from __future__ import annotations

import importlib
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

app_module = importlib.import_module("datakeel.api.app")


def test_create_app_default_empty_database_uses_backend_policy(unmigrated_db: Database) -> None:
    """SQLite needs explicit upgrade; PostgreSQL retains W3 empty-store initialization."""
    if unmigrated_db.sqlite:
        with pytest.raises(ValidationError, match=r"Database (missing|empty)"):
            create_app(unmigrated_db)
        assert inspect(unmigrated_db.engine).get_table_names() == []
    else:
        assert create_app(unmigrated_db).state.db is unmigrated_db
        assert set(inspect(unmigrated_db.engine).get_table_names()) == {
            item.table for item in canonical_schema().tables
        }


def test_create_app_disabled_skips_admission_on_empty_database(
    unmigrated_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller owns initialization; disabling it also skips the SQLite baseline check."""
    monkeypatch.setattr(app_module, "recover_runs", lambda _db: None)
    assert create_app(unmigrated_db, run_migrations=False).state.db is unmigrated_db
    assert inspect(unmigrated_db.engine).get_table_names() == []


def test_create_app_reuses_scale_facts_without_migration_or_check(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller-prepared scale fixture stays usable without changing authoritative recognition."""
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE scale_facts (value INTEGER)"))
        connection.execute(text("INSERT INTO scale_facts VALUES (7)"))

    def fail(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Explicit reuse must skip both migration and baseline checks")

    monkeypatch.setattr(Database, "migrate", fail)
    monkeypatch.setattr(app_module, "require_current", fail)
    assert create_app(db, run_migrations=False).state.db is db
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM scale_facts")).scalar_one() == 7


def test_create_app_default_rejects_unknown_table(db: Database) -> None:
    """Default admission still rejects mixed schemas on both backends."""
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE scale_facts (value INTEGER)"))
    with pytest.raises(ValidationError, match=r"Database invalid|Canonical tables mismatch"):
        create_app(db)


def test_postgres_startup_dispatches_explicit_w3_inputs_without_sqlite_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify backend dispatch offline without using a successful mock as PG execution evidence."""
    database = Database("postgresql+pg8000://localhost/unused")
    calls: list[bool] = []

    def migrate(
        db: Database,
        contributions: tuple[SchemaContribution, ...],
        *,
        canonical: CanonicalSchema,
    ) -> None:
        assert db is database
        assert contributions == schema_contributions()
        assert canonical == canonical_schema()
        calls.append(True)

    def forbidden(_db: Database) -> None:
        pytest.fail("PostgreSQL must never enter SQLite-only admission")

    monkeypatch.setattr(Database, "migrate", migrate)
    monkeypatch.setattr(app_module, "require_current", forbidden)
    monkeypatch.setattr(app_module, "recover_runs", lambda _db: None)
    try:
        assert create_app(database).state.db is database
        assert calls == [True]
        assert create_app(database, run_migrations=False).state.db is database
        assert calls == [True]
    finally:
        database.engine.dispose()
