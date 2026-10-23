# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native SQLite/PostgreSQL date functions retain resolved UTC half-open intervals."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from datakeel.ask.time import parse_time
from datakeel.core.metric_models import CompileRequest, MetricCard, TimeRange
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.execution import execute_query
from datakeel.metrics.sql_safety import validate_select

if TYPE_CHECKING:
    from datakeel.core.metric_models import SemanticLayer
    from datakeel.metrics.date_boundaries import DateDialect
    from datakeel.storage.database import Database


@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_compiler_uses_native_day_functions_with_bound_parameters(
    layer: SemanticLayer, dialect: DateDialect
) -> None:
    """The emitted SQL uses the selected dialect's actual function and no interpolated dates."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        [],
        CompileRequest(
            dialect=dialect,
            time_range=TimeRange(start=date(2025, 10, 1), end=date(2026, 1, 1)),
        ),
    )
    assert query.parameters == {"p0": "2025-10-01", "p1": "2026-01-01"}
    assert "2025-10-01" not in query.sql
    assert "2026-01-01" not in query.sql
    if dialect == "sqlite":
        assert '"date" >= DATE(:p0)' in query.sql
        assert '"date" < DATE(:p1)' in query.sql
    else:
        assert "\"date\" >= DATE_TRUNC('day', CAST(:p0 AS TIMESTAMP))" in query.sql
        assert "\"date\" < DATE_TRUNC('day', CAST(:p1 AS TIMESTAMP))" in query.sql
    assert validate_select(query.sql, dialect)


def _source_metric(db: Database, layer: SemanticLayer, interval: TimeRange) -> MetricCard:
    start = datetime.combine(interval.start, time())
    end = datetime.combine(interval.end, time())
    timestamps = (
        (1000, start - timedelta(seconds=1)),
        (1, start),
        (2, start + timedelta(seconds=1)),
        (4, end - timedelta(seconds=1)),
        (10000, end),
        (100000, end + timedelta(seconds=1)),
    )
    with db.engine.begin() as connection:
        schema = (
            "main"
            if db.sqlite
            else connection.execute(text("SELECT current_schema()")).scalar_one()
        )
        connection.execute(text("CREATE TABLE metric_dates(amount INTEGER, date TIMESTAMP)"))
        connection.execute(
            text("INSERT INTO metric_dates VALUES (:amount, :date)"),
            [{"amount": amount, "date": stamp.isoformat(sep=" ")} for amount, stamp in timestamps],
        )
    identity = f"test/{schema}/metric_dates"
    metric = layer.metrics[0]
    return MetricCard(
        definition=metric.model_copy(
            update={
                "measure": metric.measure.model_copy(
                    update={"table": identity, "column": f"{identity}/amount"}
                ),
                "time": metric.time.model_copy(update={"column": f"{identity}/date"}),
                "dimensions": [],
            }
        )
    )


@pytest.mark.parametrize(
    ("question", "start", "end"),
    [
        ("上个季度零售额", date(2025, 10, 1), date(2026, 1, 1)),
        ("2024年2月零售额", date(2024, 2, 1), date(2024, 3, 1)),
        ("近30天零售额", date(2025, 12, 16), date(2026, 1, 15)),
    ],
)
def test_native_time_queries_execute_inclusive_start_and_exclusive_end(
    db: Database, layer: SemanticLayer, question: str, start: date, end: date
) -> None:
    """Both live database matrices include midnight start and exclude midnight end exactly."""
    parsed = parse_time(question, datetime(2026, 1, 15, tzinfo=UTC))
    assert parsed.issues == ()
    assert parsed.time_range is not None
    assert parsed.time_range == TimeRange(start=start, end=end)
    card = _source_metric(db, layer, parsed.time_range)
    query = compile_metric(
        card,
        [],
        CompileRequest(dialect="sqlite" if db.sqlite else "postgres", time_range=parsed.time_range),
    )
    result = execute_query(db.engine.url.render_as_string(hide_password=False), query)
    assert result.rows == [[7]]
    assert query.parameters == {"p0": start.isoformat(), "p1": end.isoformat()}
