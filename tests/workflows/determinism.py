# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build independent identical initial stores and retain all business fields in comparisons."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from datakeel.core import models
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Generator
    from datetime import tzinfo
    from pathlib import Path

    from pydantic import JsonValue
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

UUID_TOKEN = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
TIMES = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "finished_at",
        "occurred_at",
        "expires_at",
        "elapsed_ms",
    }
)


class LogicalClock:
    """Provide ordered UTC instants with the same sequence in each independent run."""

    def __init__(self) -> None:
        """Reset time to the same fixture origin while retaining strict timestamp ordering."""
        self.ticks = count(1)

    def now(self, _timezone: tzinfo | None = None) -> datetime:
        """Advance one microsecond per timestamp requested by existing business services."""
        return datetime(2026, 10, 24, tzinfo=UTC) + timedelta(microseconds=next(self.ticks))


@contextmanager
def deterministic_clock_and_ids() -> Generator[None]:
    """Inject ID and time sources, keeping derived argument and plan digests comparable."""
    identities = count(1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(models, "uuid4", lambda: UUID(int=next(identities)))
        patch.setattr(models, "datetime", LogicalClock())
        yield


@contextmanager
def fresh_database(template: Database, directory: Path) -> Generator[Database]:
    """Create and later delete only a uniquely owned local test database or schema."""
    schema = "test_" + uuid4().hex
    database = Database(
        f"sqlite:///{directory / (schema + '.db')}"
        if template.sqlite
        else template.engine.url.render_as_string(hide_password=False)
    )
    if not database.sqlite:
        assert database.engine.url.host in {"localhost", "127.0.0.1"}
        with database.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database.engine.dispose()

        @event.listens_for(database.engine, "connect")
        def set_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
            cursor.close()

    database.migrate()
    try:
        yield database
    finally:
        if not database.sqlite:
            with database.engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        database.engine.dispose()


def comparable(value: JsonValue) -> JsonValue:
    """Remove UUID tokens and times while preserving semantic IDs, digests, and rows."""
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items() if key not in TIMES}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    return UUID_TOKEN.sub("<generated-id>", value) if isinstance(value, str) else value


def document(value: object) -> JsonDocument:
    """Validate a structured test result as a JSON boundary before comparisons."""
    return JsonDocument.model_validate(value)
