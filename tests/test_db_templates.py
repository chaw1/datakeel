# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Copied fixtures retain protections while never sharing per-test writes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from datakeel.storage.base import Base
from datakeel.storage.database import Database, DatasetRow, EventRow
from tests import db_templates
from tests.db_templates import DatabaseTemplate

if TYPE_CHECKING:
    from sqlalchemy.engine import URL


def test_copied_database_keeps_every_table_foreign_key_and_trigger(db: Database) -> None:
    """A copied schema retains real database constraints and immutable fact guards."""
    inspector = inspect(db.engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables)
    foreign_keys = inspector.get_foreign_keys("versions")
    assert any(
        key["constrained_columns"] == ["dataset_id"]
        and key["referred_table"] == "datasets"
        and key["referred_columns"] == ["id"]
        for key in foreign_keys
    )
    with pytest.raises(SQLAlchemyError, match=r"(?i)foreign key"), db.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO versions (id, dataset_id, created_at, manifest) "
                "VALUES ('orphan', 'absent', 0, '[]')"
            )
        )
    with db.session() as session:
        session.add(EventRow(event_id="protected", idempotency_key="protected", payload={}))
        session.commit()
    with pytest.raises(SQLAlchemyError, match="append-only"), db.engine.begin() as connection:
        connection.execute(text("UPDATE lineage_events SET payload='{}'"))


def test_copied_databases_never_share_data_or_schema(
    database_template: DatabaseTemplate, tmp_path: Path
) -> None:
    """Concurrent copies and later copies remain empty after one copy changes."""
    with (
        database_template.fresh(tmp_path / "first.db") as first,
        database_template.fresh(tmp_path / "second.db") as second,
    ):
        assert first.engine.url.database != second.engine.url.database
        with first.session() as session:
            session.add(DatasetRow(id="one-copy", name="Private generated data"))
            session.commit()
        with first.engine.begin() as connection:
            connection.execute(text("CREATE TABLE copy_only(value INTEGER)"))
        with second.engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM datasets")) == 0
        assert "copy_only" not in inspect(second.engine).get_table_names()
    with database_template.fresh(tmp_path / "third.db") as third:
        with third.engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM datasets")) == 0
        assert "copy_only" not in inspect(third.engine).get_table_names()


def test_upgrade_fixture_still_starts_without_application_tables(unmigrated_db: Database) -> None:
    """Migration regression tests still exercise a genuinely uninitialized schema."""
    assert inspect(unmigrated_db.engine).get_table_names() == []


def _assert_removed(url: URL, template: DatabaseTemplate) -> None:
    if template.sqlite:
        assert url.database is not None
        assert not Path(url.database).exists()
        return
    original = os.environ.get("DATAKEEL_TEST_DATABASE_URL")
    assert original is not None
    admin = create_engine(original.replace("postgresql://", "postgresql+pg8000://", 1))
    try:
        with admin.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT COUNT(*) FROM pg_database WHERE datname=:name"),
                    {"name": url.database},
                )
                == 0
            )
    finally:
        admin.dispose()


def test_failed_template_migration_removes_only_its_owned_source(
    database_template: DatabaseTemplate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An initializer failure leaves no half-migrated template database behind."""
    attempted: list[URL] = []

    def fail(database: Database) -> None:
        attempted.append(database.engine.url)
        message = "Generated migration failure"
        raise RuntimeError(message)

    monkeypatch.setattr(Database, "migrate", fail)
    with pytest.raises(RuntimeError, match="Generated migration failure"):
        DatabaseTemplate(os.environ.get("DATAKEEL_TEST_DATABASE_URL"), tmp_path)
    assert len(attempted) == 1
    _assert_removed(attempted[0], database_template)


def test_failed_test_disposes_the_copy_without_mutating_the_template(
    database_template: DatabaseTemplate, tmp_path: Path
) -> None:
    """Exceptional exits remove owned PostgreSQL copies and keep later copies usable."""
    copied: list[URL] = []

    def fail() -> None:
        with database_template.fresh(tmp_path / "failed.db") as database:
            copied.append(database.engine.url)
            message = "Generated test failure"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="Generated test failure"):
        fail()
    assert len(copied) == 1
    _assert_removed(copied[0], database_template)
    with database_template.fresh(tmp_path / "after.db") as database:
        assert set(inspect(database.engine).get_table_names()) == set(Base.metadata.tables)


def test_failed_copy_initialization_removes_its_owned_database(
    database_template: DatabaseTemplate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed engine constructor cannot leak a newly created PostgreSQL clone."""
    attempted: list[URL] = []

    def fail(url: str) -> Database:
        attempted.append(db_templates.make_url(url))
        message = "Generated engine failure"
        raise RuntimeError(message)

    def create_copy() -> None:
        with database_template.fresh(tmp_path / "failed-copy.db"):
            pytest.fail("The generated constructor failure must prevent a usable copy")

    monkeypatch.setattr(db_templates, "Database", fail)
    with pytest.raises(RuntimeError, match="Generated engine failure"):
        create_copy()
    assert len(attempted) == 1
    _assert_removed(attempted[0], database_template)


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling"])
def test_existing_copy_destination_is_never_overwritten(
    database_template: DatabaseTemplate, tmp_path: Path, kind: str
) -> None:
    """An existing caller-owned path prevents creating or changing a database copy."""
    path = tmp_path / "existing.db"
    target = tmp_path / "target.db"
    content = b"Generated existing destination"
    if kind == "file":
        path.write_bytes(content)
    else:
        if kind == "symlink":
            target.write_bytes(content)
        path.symlink_to(target)

    def create_copy() -> None:
        with database_template.fresh(path):
            pytest.fail("The existing destination must prevent a usable copy")

    with pytest.raises(FileExistsError):
        create_copy()
    assert path.is_symlink() == (kind != "file")
    if kind == "dangling":
        assert not target.exists()
    else:
        assert path.read_bytes() == content
