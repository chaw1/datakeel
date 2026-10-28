# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read bounded source values without losing decimal precision or SQLite boolean intent."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, cast

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from datakeel.core.catalog_identity import catalog_segments
from datakeel.core.catalog_models import CatalogObject, SourceProperties
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.standard_models import ColumnProfile, StandardValue
from datakeel.metrics.sql_safety import validate_select
from datakeel.standards.names import canonical_type

if TYPE_CHECKING:
    import sqlite3

_MAX_ROWS = 10000
_TIMEOUT_MS = 5000


def _source_url(connection_url: str) -> URL:
    try:
        url = make_url(connection_url)
    except ArgumentError as exc:
        msg = "Invalid standards observation source URL"
        raise ValidationError(msg) from exc
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            msg = "Standards observation requires an existing SQLite source file"
            raise ValidationError(msg)
        path = Path(url.database).resolve()
        if not path.is_file():
            msg = "Standards observation source file does not exist"
            raise ValidationError(msg)
        return url.set(database=f"file:{path}", query={"mode": "ro", "uri": "true"})
    if url.get_backend_name() == "postgresql":
        return url.set(drivername="postgresql+pg8000")
    msg = "Standards observations support SQLite and PostgreSQL sources"
    raise ValidationError(msg)


def _protect(connection: Connection) -> None:
    if connection.dialect.name == "sqlite":
        raw = cast("sqlite3.Connection", connection.connection.driver_connection)
        raw.execute("PRAGMA query_only=ON")
        deadline = monotonic() + _TIMEOUT_MS / 1000
        raw.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
    else:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(_TIMEOUT_MS)},
        )


def _scalar(value: object, data_type: str) -> StandardValue:
    if canonical_type(data_type) == "boolean" and type(value) is int and value in {0, 1}:
        return bool(value)
    if value is None or isinstance(value, str | int | float | bool | Decimal):
        return value
    if isinstance(value, date | datetime):
        return value.isoformat()
    msg = f"Unsupported standards observation scalar: {type(value).__name__}"
    raise ExecutionError(msg)


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_observations(
    source: SourceProperties, table: CatalogObject, profiles: tuple[ColumnProfile, ...]
) -> tuple[ColumnProfile, ...]:
    """Run only a bounded authored SELECT under database-enforced read-only protections."""
    if not profiles:
        return ()
    qualified = ".".join(_quoted(item) for item in catalog_segments(table.asset_ref.asset_id)[-2:])
    names = ", ".join(_quoted(item.name) for item in profiles)
    # Every identifier is registered metadata and is individually quoted; LIMIT is authored.
    sql = f"SELECT {names} FROM {qualified} LIMIT {_MAX_ROWS + 1}"  # noqa: S608
    validate_select(sql, "sqlite" if source.dialect == "sqlite" else "postgres")
    engine = create_engine(_source_url(source.connection_url or ""))
    try:
        with engine.connect() as connection:
            _protect(connection)
            rows = connection.execute(text(sql)).fetchmany(_MAX_ROWS + 1)
            return tuple(
                _observed(
                    profile,
                    tuple(_scalar(row[index], profile.data_type) for row in rows[:_MAX_ROWS]),
                    truncated=len(rows) > _MAX_ROWS,
                )
                for index, profile in enumerate(profiles)
            )
    except SQLAlchemyError as exc:
        msg = f"Read-only standards observation failed: {type(exc).__name__}"
        raise ExecutionError(msg) from exc
    finally:
        engine.dispose()


def _observed(
    profile: ColumnProfile, values: tuple[StandardValue, ...], *, truncated: bool
) -> ColumnProfile:
    return profile.model_copy(
        update={
            "values": values,
            "row_count": len(values),
            "null_count": sum(value is None for value in values),
            "truncated": truncated,
        }
    )
