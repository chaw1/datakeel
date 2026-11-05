# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One transactional fact store, with SQLite and PostgreSQL dialects."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import (
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from datakeel.core.errors import NotFoundError
from datakeel.core.schema import (
    Base,
    CanonicalSchema,
    SchemaContribution,
    validate_contributions,
    validate_tables,
)
from datakeel.core.settings import get_settings
from datakeel.storage.migrations import add_nullable_columns

if TYPE_CHECKING:
    import sqlite3

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


def data_dir() -> Path:
    """Resolve and initialize the configured local data directory."""
    path = get_settings().home.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_only_sqlite_url(url: str) -> str:
    """Require an existing SQLite file and prevent journal or schema writes."""
    parsed = make_url(url)
    database = parsed.database
    if not database or database == ":memory:" or not Path(database).is_file():
        msg = "Trace database does not exist; run datakeel migrate first"
        raise NotFoundError(msg)
    return str(
        parsed.set(database=f"file:{database}", query={**parsed.query, "mode": "ro", "uri": "true"})
    )


class Database:
    """Own a database engine and short-lived transactional sessions."""

    def __init__(self, url: str | None = None, *, read_only: bool = False) -> None:
        """Connect to the selected local or explicitly configured database."""
        if url is None:
            settings = get_settings()
            url = settings.database_url or f"sqlite:///{settings.home.resolve() / 'datakeel.db'}"
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        if read_only and url.startswith("sqlite"):
            url = _read_only_sqlite_url(url)
        self.engine: Engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
            pool_pre_ping=True,
        )
        self.sqlite = self.engine.dialect.name == "sqlite"
        if self.sqlite:

            @event.listens_for(self.engine, "connect")
            def configure(connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=30000")
                if not read_only:
                    connection.execute("PRAGMA journal_mode=WAL")
        elif read_only:

            @event.listens_for(self.engine, "connect")
            def configure_read_only(
                connection: DBAPIConnection, _record: ConnectionPoolEntry
            ) -> None:
                cursor = connection.cursor()
                cursor.execute("SET default_transaction_read_only = on")
                cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        """Create a session whose caller owns commit or rollback."""
        return self.sessions()

    def migrate(
        self, contributions: tuple[SchemaContribution, ...], *, canonical: CanonicalSchema
    ) -> None:
        """Validate explicit schema inputs, then migrate under the existing write lock."""
        validate_contributions(contributions, canonical)
        with self.engine.begin() as connection:
            if self.sqlite:
                connection.execute(text("BEGIN IMMEDIATE"))
            else:
                connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtext('datakeel:migrate:' || current_schema()))"
                    )
                )
            Base.metadata.create_all(connection)
            add_nullable_columns(connection)
            installers = sorted(
                (item for contribution in contributions for item in contribution.installers),
                key=lambda item: item.order,
            )
            for installer in installers:
                installer.install(connection, sqlite=self.sqlite)
            validate_tables(frozenset(inspect(connection).get_table_names()), canonical)

    def lock_writes(self, session: Session) -> None:
        """Serialize SQLite writers to match PostgreSQL row-lock semantics."""
        if self.sqlite:
            session.execute(text("BEGIN IMMEDIATE"))
