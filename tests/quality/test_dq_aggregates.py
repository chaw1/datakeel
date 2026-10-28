# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Volume and freshness rules aggregate inside the business database, beyond any scan cap."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema, DropSchema

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.quality import dq_source
from datakeel.quality.dq_engine import execute_rule

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.core.dq_models import DqKind
    from datakeel.core.metric_models import CompiledQuery, QueryLimits, QueryResult
    from datakeel.storage.database import Database

NOW = datetime(2026, 10, 27, 8, tzinfo=UTC)
ROWS = 120_001  # Larger than the highest per-rule scan cap (100,000 rows).


@pytest.fixture
def large_source(db: Database, tmp_path: Path) -> Iterator[tuple[SourceProperties, str]]:
    """A dispatch log whose text-sorted maximum is not its chronological maximum."""
    if db.sqlite:
        path = tmp_path / "dispatch.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE dispatch(id INTEGER, sent_at TEXT, idle_at TEXT)")
            connection.execute(
                "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < ?) "
                "INSERT INTO dispatch SELECT i, '2026-10-27T01:00:00+00:00', NULL FROM n",
                (ROWS - 2,),
            )
            # 13:30+08:00 sorts after 06:00Z as text but is 05:30Z, so 06:00Z is newest.
            connection.executemany(
                "INSERT INTO dispatch VALUES (?, ?, ?)",
                [(-1, "2026-10-27T13:30:00+08:00", None), (-2, "2026-10-27T06:00:00Z", None)],
            )
        url, schema = f"sqlite:///{path}", "main"
    else:
        url = db.engine.url.render_as_string(hide_password=False)
        schema = "dq_aggregate_" + uuid4().hex
        with db.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            connection.execute(
                text("CREATE TABLE dispatch(id INTEGER, sent_at TIMESTAMPTZ, idle_at TIMESTAMPTZ)")
            )
            connection.execute(
                text(
                    "INSERT INTO dispatch SELECT i, TIMESTAMPTZ '2026-10-27 01:00:00+00', NULL "
                    "FROM generate_series(1, :rows) AS i"
                ),
                {"rows": ROWS - 2},
            )
            connection.execute(
                text(
                    "INSERT INTO dispatch VALUES "
                    "(-1, TIMESTAMPTZ '2026-10-27 13:30:00+08', NULL), "
                    "(-2, TIMESTAMPTZ '2026-10-27 06:00:00+00', NULL)"
                )
            )
    try:
        yield (
            SourceProperties(connection_url=url, dialect="sqlite" if db.sqlite else "postgresql"),
            schema,
        )
    finally:
        if not db.sqlite:
            with db.engine.begin() as connection:
                # Only this fixture's newly generated UUID schema is removed.
                connection.execute(DropSchema(schema, cascade=True))


def _rule(schema: str, kind: DqKind, column: str | None, threshold: float) -> DqRule:
    return DqRule(
        id=f"dispatch-{kind}".replace("_", "-"),
        name="Dispatch log rule",
        owner="quality-team",
        kind=kind,
        target=DqTarget(source_id="dispatch", schema_name=schema, table="dispatch", column=column),
        params=DqParameters(baseline_runs=1),
        threshold=threshold,
        max_rows=100_000,
    )


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    statements: list[str] = []
    original = dq_source.execute_query

    def recording(url: str, query: CompiledQuery, limits: QueryLimits | None = None) -> QueryResult:
        statements.append(query.sql)
        return original(url, query, limits)

    monkeypatch.setattr(dq_source, "execute_query", recording)
    return statements


def test_volume_and_freshness_aggregate_beyond_the_scan_cap(
    large_source: tuple[SourceProperties, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One COUNT/MAX statement per run, no row limit, and chronological latest timestamps."""
    source, schema = large_source
    statements = _capture(monkeypatch)
    volume = _rule(schema, "volume_change", None, 0.1)
    previous = execute_rule(volume, source, now=NOW - timedelta(days=1))
    assert (previous.status, previous.row_count) == ("baseline_insufficient", ROWS)
    current = execute_rule(volume, source, (previous,), NOW)
    assert (current.status, current.actual_value, current.row_count) == ("passed", 0.0, ROWS)
    fresh = execute_rule(_rule(schema, "freshness", "sent_at", 3 * 3600), source, now=NOW)
    assert (fresh.status, fresh.actual_value, fresh.row_count) == ("passed", 7200.0, ROWS)
    assert len(statements) == 3
    assert all("COUNT(*)" in sql and "LIMIT" not in sql.upper() for sql in statements)


def test_unparsable_timestamp_cells_fail_freshness(
    db: Database, large_source: tuple[SourceProperties, str]
) -> None:
    """'now', bare Julian numbers, other types and infinities never look like fresh data."""
    source, schema = large_source
    if db.sqlite:
        path = source.connection_url.removeprefix("sqlite:///") if source.connection_url else ""
        with sqlite3.connect(path) as connection:
            connection.executemany(
                "INSERT INTO dispatch VALUES (?, ?, NULL)",
                [(-3, "now"), (-4, "2461340.5"), (-5, 2461340.5), (-6, "27/10/2026")],
            )
        invalid = 4
    else:
        with db.engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            connection.execute(
                text(
                    "INSERT INTO dispatch VALUES "
                    "(-3, TIMESTAMPTZ 'infinity', NULL), (-4, TIMESTAMPTZ '-infinity', NULL)"
                )
            )
        invalid = 2
    result = execute_rule(_rule(schema, "freshness", "sent_at", 3 * 3600), source, now=NOW)
    assert result.status == "failed"
    assert result.message == f"{invalid} non-NULL cells are not valid timestamps"
    empty = execute_rule(_rule(schema, "freshness", "idle_at", 3 * 3600), source, now=NOW)
    assert (empty.status, empty.message) == ("failed", "No valid latest timestamp is available")
