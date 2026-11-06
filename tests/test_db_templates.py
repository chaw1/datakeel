# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Copied fixtures retain protections while never sharing per-test writes."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from datakeel.dataset_store.rows import DatasetRow, EventRow
from datakeel.persistence.canonical import canonical_schema
from datakeel.storage.base import Base
from tests import db_templates
from tests.db_templates import DatabaseTemplate, restart_database

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

    from datakeel.storage.database import Database


def test_copied_database_keeps_every_table_foreign_key_and_trigger(db: Database) -> None:
    """A copied schema retains real database constraints and immutable fact guards."""
    inspector = inspect(db.engine)
    assert set(inspector.get_table_names()) - {"datakeel_schema_versions"} == set(
        Base.metadata.tables
    )
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
    if not unmigrated_db.sqlite:
        with unmigrated_db.engine.connect() as connection:
            schema = connection.scalar(text("SELECT current_schema()"))
            assert isinstance(schema, str)
            assert schema.startswith("test_")
    assert inspect(unmigrated_db.engine).get_table_names() == []
    with unmigrated_db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE fixture_probe(value INTEGER)"))
    unmigrated_db.engine.dispose()
    assert inspect(unmigrated_db.engine).get_table_names() == ["fixture_probe"]


def test_restarted_engine_keeps_private_schema_on_every_concurrent_connection(db: Database) -> None:
    """A restart and pool disposal retain the exact path, tables and private rows."""
    with db.session() as session:
        session.add(DatasetRow(id="restart-private", name="Generated restart fixture"))
        session.commit()
    restarted = restart_database(db)
    barrier = Barrier(3)

    def read_copy(_: int) -> str | None:
        with restarted.engine.connect() as connection:
            barrier.wait(timeout=10)
            if not db.sqlite:
                with db.engine.connect() as original:
                    expected = original.scalar(text("SHOW search_path"))
                assert connection.scalar(text("SHOW search_path")) == expected
                assert connection.scalar(text("SELECT current_schema()")) != "public"
                assert (
                    connection.scalar(text("SELECT to_regclass('public.vector_fake_attempts')"))
                    is None
                )
            assert "vector_fake_attempts" in inspect(connection).get_table_names()
            return connection.scalar(text("SELECT id FROM datasets"))

    try:
        restarted.engine.dispose()
        with ThreadPoolExecutor(max_workers=3) as pool:
            assert list(pool.map(read_copy, range(3))) == ["restart-private"] * 3
    finally:
        restarted.engine.dispose()


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
    original = db_templates.migrate

    def fail(database: Database) -> None:
        attempted.append(database.engine.url)
        original(database)
        assert set(inspect(database.engine).get_table_names()) - {"datakeel_schema_versions"} == {
            item.table for item in canonical_schema().tables
        }
        message = "Generated migration failure"
        raise RuntimeError(message)

    monkeypatch.setattr(db_templates, "migrate", fail)
    with pytest.raises(RuntimeError, match="Generated migration failure"):
        DatabaseTemplate(os.environ.get("DATAKEEL_TEST_DATABASE_URL"), tmp_path)
    assert len(attempted) == 1
    _assert_removed(attempted[0], database_template)
    with database_template.fresh(tmp_path / "surviving-copy.db") as database:
        assert set(inspect(database.engine).get_table_names()) - {"datakeel_schema_versions"} == {
            item.table for item in canonical_schema().tables
        }


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
        assert set(inspect(database.engine).get_table_names()) - {
            "datakeel_schema_versions"
        } == set(Base.metadata.tables)


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
