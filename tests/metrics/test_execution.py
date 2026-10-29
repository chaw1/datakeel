# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actual source connections enforce query-only access, row caps, and time bounds."""

from datetime import date

import pytest
from sqlalchemy import text

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metric_models import (
    CompileRequest,
    DimensionSlice,
    MetricCard,
    QueryLimits,
    SemanticLayer,
    TimeRange,
)
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.execution import execute_query
from datakeel.storage.database import Database


def test_execute_query_filters_match_gold(source_url: str, layer: SemanticLayer) -> None:
    """Execute date bounds and a region slice against an existing SQLite file."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        layer.dimensions,
        CompileRequest(
            slices=[DimensionSlice(dimension_id="region", value="华东")],
            time_range=TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1)),
        ),
    )
    assert execute_query(source_url, query).rows == [[30.0]]


def test_execute_query_injection_value_remains_literal(
    source_url: str, layer: SemanticLayer
) -> None:
    """A stored injection-looking region value selects exactly that region."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        layer.dimensions,
        CompileRequest(
            slices=[DimensionSlice(dimension_id="region", value="华东' OR 1=1 --")],
        ),
    )
    assert execute_query(source_url, query).rows == [[160.0]]


def test_execute_query_row_limit_and_truncation(source_url: str, layer: SemanticLayer) -> None:
    """Fetch at most one extra row to report truncation accurately."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        layer.dimensions,
        CompileRequest(group_by=["region"]),
    )
    result = execute_query(source_url, query, QueryLimits(max_rows=1))
    assert len(result.rows) == 1
    assert result.truncated


def test_execute_query_rejects_writes_before_connecting(
    source_url: str, layer: SemanticLayer
) -> None:
    """Forging the query boundary cannot bypass the independent execution guard."""
    query = compile_metric(MetricCard(definition=layer.metrics[0]), [], CompileRequest())
    query = query.model_copy(update={"sql": "DELETE FROM orders"})
    with pytest.raises(ValidationError, match="SELECT"):
        execute_query(source_url, query)


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "mysql://localhost/test"])
def test_execute_query_unsupported_sources_are_rejected(url: str, layer: SemanticLayer) -> None:
    """A missing SQLite file or unsupported backend never creates a writable source."""
    query = compile_metric(MetricCard(definition=layer.metrics[0]), [], CompileRequest())
    with pytest.raises(ValidationError):
        execute_query(url, query)


def test_execute_query_missing_table_becomes_domain_error(
    source_url: str, layer: SemanticLayer
) -> None:
    """Database exceptions are surfaced without leaking source credentials."""
    query = compile_metric(MetricCard(definition=layer.metrics[0]), [], CompileRequest())
    query = query.model_copy(update={"sql": "SELECT * FROM absent"})
    with pytest.raises(ExecutionError, match="Read-only metric query failed"):
        execute_query(source_url, query)


def test_execute_query_sqlite_timeout_aborts_expensive_select(
    source_url: str, layer: SemanticLayer
) -> None:
    """The VM progress handler interrupts work even before any rows are returned."""
    query = compile_metric(MetricCard(definition=layer.metrics[0]), [], CompileRequest())
    query = query.model_copy(
        update={
            "sql": (
                "WITH RECURSIVE numbers(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM numbers "
                "WHERE x < 1000000000) SELECT sum(x) FROM numbers"
            )
        }
    )
    with pytest.raises(ExecutionError):
        execute_query(source_url, query, QueryLimits(timeout_ms=1))


def test_query_scalars_reject_unsupported_database_values(
    source_url: str, layer: SemanticLayer
) -> None:
    """Reject an actual SQLite BLOB at the public scalar result boundary."""
    query = compile_metric(MetricCard(definition=layer.metrics[0]), [], CompileRequest())
    binary = query.model_copy(update={"sql": "SELECT X'01' AS unsupported_blob"})
    with pytest.raises(ExecutionError, match="Unsupported"):
        execute_query(source_url, binary)


def test_execute_query_postgres_real_transaction(db: Database, layer: SemanticLayer) -> None:
    """The local PostgreSQL matrix runs actual dialect SQL and enforces read-only timeout."""
    if db.sqlite:
        pytest.skip("PostgreSQL execution is exercised by the local PostgreSQL matrix")
    with db.engine.begin() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        connection.execute(text("CREATE TABLE metric_orders(amount NUMERIC, date DATE)"))
        connection.execute(
            text("INSERT INTO metric_orders VALUES (12.5, '2026-07-01'), (7.5, '2026-09-01')")
        )
    measure = layer.metrics[0].measure.model_copy(
        update={
            "table": f"test/{schema}/metric_orders",
            "column": f"test/{schema}/metric_orders/amount",
        }
    )
    metric = layer.metrics[0].model_copy(
        update={
            "measure": measure,
            "time": layer.metrics[0].time.model_copy(
                update={"column": f"test/{schema}/metric_orders/date"}
            ),
            "dimensions": [],
        }
    )
    query = compile_metric(
        MetricCard(definition=metric),
        [],
        CompileRequest(
            dialect="postgres",
            time_range=TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1)),
        ),
    )
    source_url = db.engine.url.render_as_string(hide_password=False)
    assert execute_query(source_url, query).rows == [[20.0]]
    for grain in ("day", "month", "quarter", "year"):
        grouped = compile_metric(
            MetricCard(definition=metric),
            [],
            CompileRequest(dialect="postgres", time_grain=grain),
        )
        expected = (
            [["2026-07-01", 12.5], ["2026-09-01", 7.5]]
            if grain in {"day", "month"}
            else [["2026-07-01" if grain == "quarter" else "2026-01-01", 20.0]]
        )
        assert execute_query(source_url, grouped).rows == expected
    scalars = query.model_copy(
        update={"sql": "SELECT CAST(1.25 AS NUMERIC) AS amount, DATE '2026-07-01' AS date"}
    )
    assert execute_query(source_url, scalars).rows == [[1.25, "2026-07-01"]]
    sleeping = query.model_copy(update={"sql": "SELECT pg_sleep(10)"})
    with pytest.raises(ExecutionError):
        execute_query(source_url, sleeping, QueryLimits(timeout_ms=1))
    mutating = query.model_copy(update={"sql": "SELECT nextval('missing_sequence')"})
    with pytest.raises(ExecutionError):
        execute_query(source_url, mutating)
