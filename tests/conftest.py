# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fresh fact stores and object directories, never shared application state."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from datakeel.storage.database import Database
from tests.db_templates import DatabaseTemplate

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


@pytest.fixture
def unmigrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    """Provide an isolated database before schema initialization for upgrade tests."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    url = os.environ.get("DATAKEEL_TEST_DATABASE_URL")
    database = Database(url or f"sqlite:///{tmp_path / 'test.db'}")
    schema = "test_" + uuid4().hex
    if not database.sqlite:
        assert database.engine.url.host in ("localhost", "127.0.0.1"), (
            "Tests only allow a new local instance"
        )
        with database.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database.engine.dispose()

        @event.listens_for(database.engine, "connect")
        def set_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            """Provide the set schema test fixture."""
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
            cursor.close()

    yield database
    if not database.sqlite:
        with database.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    database.engine.dispose()


@pytest.fixture(scope="session")
def database_template(tmp_path_factory: pytest.TempPathFactory) -> Iterator[DatabaseTemplate]:
    """Migrate one empty source per process while preserving independent test copies."""
    template = DatabaseTemplate(
        os.environ.get("DATAKEEL_TEST_DATABASE_URL"), tmp_path_factory.mktemp("database-template")
    )
    try:
        yield template
    finally:
        template.close()


@pytest.fixture
def db(
    database_template: DatabaseTemplate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Database]:
    """Provide a migrated copy with private facts, constraints, and object storage."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    with database_template.fresh(tmp_path / "test.db") as database:
        yield database
