# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Connection setup and SQLite lock waits share the declared query deadline."""

import sqlite3
from pathlib import Path
from time import monotonic

import pg8000
import pytest

from datakeel.core.errors import ExecutionError
from datakeel.core.metric_models import CompiledQuery, QueryLimits
from datakeel.metrics.execution import execute_query


def query() -> CompiledQuery:
    """Construct a harmless query independently of the semantic compiler."""
    return CompiledQuery(
        metric_id="generated",
        metric_version=1,
        source_id="generated",
        dialect="sqlite",
        sql="SELECT value FROM observations",
        tables=["observations"],
        columns=["value"],
    )


@pytest.mark.parametrize("error_type", [pg8000.InterfaceError, TimeoutError])
def test_postgres_socket_timeout_is_passed_without_opening_network(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    """The installed pg8000 adapter receives the query's socket/connect timeout."""
    captured: list[object] = []

    def blocked_connect(**kwargs: object) -> None:
        captured.append(kwargs["timeout"])
        msg = "Generated connection timeout"
        raise error_type(msg)

    monkeypatch.setattr(pg8000, "connect", blocked_connect)
    with pytest.raises(ExecutionError, match="Read-only metric query failed"):
        execute_query(
            "postgresql://unreachable.invalid/generated",
            query().model_copy(update={"dialect": "postgres"}),
            QueryLimits(timeout_ms=25),
        )
    assert captured == [0.025]


def test_sqlite_exclusive_lock_wait_obeys_query_timeout(tmp_path: Path) -> None:
    """A locked business file cannot retain SQLite's default multi-second busy wait."""
    path = tmp_path / "locked.sqlite"
    with sqlite3.connect(path) as writer:
        writer.execute("CREATE TABLE observations(value INTEGER)")
        writer.execute("INSERT INTO observations VALUES (1)")
        writer.commit()
        writer.execute("BEGIN EXCLUSIVE")
        started = monotonic()
        with pytest.raises(ExecutionError):
            execute_query(f"sqlite:///{path}", query(), QueryLimits(timeout_ms=20))
        elapsed = monotonic() - started
        writer.rollback()
    assert elapsed < 1


def test_connection_setup_exhausts_injected_whole_query_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Time spent connecting is deducted before any business SELECT can begin."""
    path = tmp_path / "deadline.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations(value INTEGER)")
    ticks = iter((0.0, 1.0))
    monkeypatch.setattr("datakeel.metrics.execution.monotonic", lambda: next(ticks))
    with pytest.raises(ExecutionError, match="connection exceeded"):
        execute_query(f"sqlite:///{path}", query(), QueryLimits(timeout_ms=20))
