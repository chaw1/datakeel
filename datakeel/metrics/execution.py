# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute compiler output through read-only connections with strict resource caps."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import SQLAlchemyError

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metric_models import CompiledQuery, QueryLimits, QueryResult, Scalar
from datakeel.metrics.sql_safety import validate_select

if TYPE_CHECKING:
    import sqlite3


def execute_query(
    source_url: str, query: CompiledQuery, limits: QueryLimits | None = None
) -> QueryResult:
    """Run a validated SELECT using database-enforced read-only permissions."""
    limits = limits or QueryLimits()
    return execute_queries(source_url, (query,), limits)[0]


def execute_queries(
    source_url: str, queries: tuple[CompiledQuery, ...], limits: QueryLimits
) -> tuple[QueryResult, ...]:
    """Read bounded results in a single protected snapshot, without mixing source revisions."""
    if not queries:
        return ()
    for query in queries:
        validate_select(query.sql, query.dialect)
    with _read_connection(source_url, queries[0], limits) as connection:
        return tuple(_read_result(connection, query, limits) for query in queries)


def _read_result(connection: Connection, query: CompiledQuery, limits: QueryLimits) -> QueryResult:
    result = connection.execute(text(query.sql), query.parameters)
    rows = result.fetchmany(limits.max_rows + 1)
    return QueryResult(
        columns=list(result.keys()),
        rows=[[_scalar(value) for value in row] for row in rows[: limits.max_rows]],
        truncated=len(rows) > limits.max_rows,
    )


def stream_query(
    source_url: str, query: CompiledQuery, limits: QueryLimits
) -> Iterator[QueryResult]:
    """Yield bounded batches from one protected transaction, using server cursors on PostgreSQL."""
    deadline = monotonic() + limits.timeout_ms / 1000
    size = min(limits.max_rows, 4096)
    with _read_connection(source_url, query, limits) as connection:
        result = connection.execution_options(yield_per=size).execute(
            text(query.sql), query.parameters
        )
        try:
            while rows := result.fetchmany(size):
                if monotonic() >= deadline:
                    msg = "Read-only query stream exceeded its timeout"
                    raise ExecutionError(msg)
                yield QueryResult(
                    columns=list(result.keys()),
                    rows=[[_scalar(value) for value in row] for row in rows],
                )
        finally:
            result.close()


@contextmanager
def _read_connection(
    source_url: str, query: CompiledQuery, limits: QueryLimits
) -> Generator[Connection]:
    deadline = monotonic() + limits.timeout_ms / 1000
    validate_select(query.sql, query.dialect)
    url = make_url(source_url)
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            msg = "Read-only metric execution requires an existing SQLite source file"
            raise ValidationError(msg)
        path = Path(url.database).resolve()
        url = url.set(database=f"file:{path}", query={"mode": "ro", "uri": "true"})
    elif url.get_backend_name() == "postgresql":
        url = url.set(drivername="postgresql+pg8000")
    else:
        msg = "Metric execution supports SQLite and PostgreSQL sources"
        raise ValidationError(msg)
    engine = create_engine(url, connect_args={"timeout": limits.timeout_ms / 1000})
    try:
        with engine.connect() as connection:
            remaining = int((deadline - monotonic()) * 1000)
            if remaining < 1:
                msg = "Read-only query connection exceeded its timeout"
                raise ExecutionError(msg)
            limits = limits.model_copy(update={"timeout_ms": remaining})
            _protect(connection, limits)
            yield connection
    except (SQLAlchemyError, OSError) as exc:
        msg = f"Read-only metric query failed: {type(exc).__name__}"
        raise ExecutionError(msg) from exc
    finally:
        engine.dispose()


def _protect(connection: Connection, limits: QueryLimits) -> None:
    if connection.dialect.name == "sqlite":
        raw = cast("sqlite3.Connection", connection.connection.driver_connection)
        raw.execute("PRAGMA query_only=ON")
        raw.execute("BEGIN")
        raw.execute(f"PRAGMA busy_timeout={limits.timeout_ms}")
        deadline = monotonic() + limits.timeout_ms / 1000
        raw.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
    else:
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(limits.timeout_ms)},
        )


def _scalar(value: object) -> Scalar:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    msg = f"Unsupported query result scalar: {type(value).__name__}"
    raise ExecutionError(msg)
