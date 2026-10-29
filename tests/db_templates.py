# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Copy fully migrated empty stores without sharing mutable database state."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from sqlalchemy.engine import URL, Engine
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


def _remove_sqlite(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def _open_pooled_connection(database: Database) -> None:
    """Leave one ready pooled connection, as the original fixture's migration did.

    Offline tests forbid new sockets after setup and rely on that fixture connection.
    """
    with database.engine.connect():
        pass


def schema_database(url: URL, schema: str) -> Database:
    """Retain the original fixture's engine initialization and per-connection schema."""
    database = Database(url.render_as_string(hide_password=False))
    try:
        # Initialize the dialect in public before installing the fixture schema hook.
        with database.engine.connect():
            pass
        database.engine.dispose()

        @event.listens_for(database.engine, "connect")
        def set_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
            cursor.close()

    except BaseException:
        database.engine.dispose()
        raise
    return database


class DatabaseTemplate:
    """Own one immutable migrated source and freshly copied per-test fact stores."""

    def __init__(self, url: str | None, directory: Path) -> None:
        """Migrate a private empty source, removing owned resources on any failure."""
        self._path = directory / f"template-{uuid4().hex}.sqlite"
        self._url = make_url(url or f"sqlite:///{self._path}")
        if self._url.drivername == "postgresql":
            self._url = self._url.set(drivername="postgresql+pg8000")
        self.sqlite = self._url.get_backend_name() == "sqlite"
        self._schema = "test_" + uuid4().hex
        self._source: str | None = None
        self._owned: set[str] = set()
        self._admin: Engine | None = None
        try:
            self._initialize()
        except BaseException:
            self.close()
            raise

    def _initialize(self) -> None:
        if self.sqlite:
            database = Database(f"sqlite:///{self._path}")
        else:
            assert self._url.host in {"localhost", "127.0.0.1"}, (
                "Tests only allow a new local instance"
            )
            self._admin = create_engine(self._url, isolation_level="AUTOCOMMIT")
            self._source = "datakeel_template_" + uuid4().hex
            self._create_database(self._source, "template0")
            url = self._url.set(database=self._source)
            initial = Database(url.render_as_string(hide_password=False))
            try:
                with initial.engine.begin() as connection:
                    connection.execute(text(f'CREATE SCHEMA "{self._schema}"'))
            finally:
                initial.engine.dispose()
            database = schema_database(url, self._schema)
        try:
            database.migrate()
        finally:
            database.engine.dispose()

    def _create_database(self, name: str, source: str) -> None:
        assert self._admin is not None
        with self._admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{source}"'))
        self._owned.add(name)

    def _drop_database(self, name: str) -> None:
        assert name in self._owned
        assert self._admin is not None
        # Like the original DROP SCHEMA, removal must not depend on the test having closed
        # every session. FORCE ends only sessions on this UUID database owned by this fixture.
        with self._admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        self._owned.remove(name)

    @contextmanager
    def fresh(self, path: Path) -> Generator[Database]:
        """Provide a complete independent schema copy and dispose it after the test."""
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        if self.sqlite:
            database = None
            try:
                with (
                    closing(sqlite3.connect(self._path)) as source,
                    closing(sqlite3.connect(path)) as destination,
                ):
                    source.backup(destination)
                database = Database(f"sqlite:///{path}")
                _open_pooled_connection(database)
                yield database
            finally:
                if database is not None:
                    database.engine.dispose()
                _remove_sqlite(path)
            return
        assert self._source is not None
        name = "datakeel_test_" + uuid4().hex
        self._create_database(name, self._source)
        database = None
        try:
            database = schema_database(self._url.set(database=name), self._schema)
            _open_pooled_connection(database)
            yield database
        finally:
            if database is not None:
                database.engine.dispose()
            self._drop_database(name)

    def close(self) -> None:
        """Remove only databases proven to have been created by this template owner."""
        try:
            for name in tuple(self._owned):
                self._drop_database(name)
        finally:
            if self._admin is not None:
                self._admin.dispose()
            if self.sqlite:
                _remove_sqlite(self._path)
