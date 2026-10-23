# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Registered-only compilation binds values and refuses every SQL write form."""

from datetime import date

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import (
    CompileRequest,
    DimensionSlice,
    MetricCard,
    MetricFilter,
    SemanticLayer,
    TimeRange,
)
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.compiler_filters import column_expression, identifier
from datakeel.metrics.sql_safety import validate_select


def test_compile_metric_slices_dates_and_groups_are_parameterized(layer: SemanticLayer) -> None:
    """Combine grouping, time intervals, and hostile text without SQL interpolation."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        layer.dimensions,
        CompileRequest(
            slices=[DimensionSlice(dimension_id="region", value="华东' OR 1=1 --")],
            group_by=["region"],
            time_range=TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1)),
        ),
    )
    assert "华东" not in query.sql
    assert query.parameters == {"p0": "华东' OR 1=1 --", "p1": "2026-07-01", "p2": "2026-10-01"}
    assert "GROUP BY" in query.sql
    assert "ORDER BY" in query.sql
    assert query.columns == [
        "test/main/orders/amount",
        "test/main/orders/date",
        "test/main/orders/region",
    ]


def test_compile_metric_postgres_retains_portable_bindings(layer: SemanticLayer) -> None:
    """Transpile registered identifiers and keep named binds for SQLAlchemy."""
    metric = layer.metrics[0].model_copy(
        update={
            "filters": [
                MetricFilter(
                    column="test/main/orders/region",
                    value="华东",
                )
            ]
        }
    )
    query = compile_metric(
        MetricCard(definition=metric), layer.dimensions, CompileRequest(dialect="postgres")
    )
    assert ":p0" in query.sql
    assert query.parameters == {"p0": "华东"}
    assert validate_select(query.sql, "postgres")


@pytest.mark.parametrize("aggregation", ["count", "avg", "min", "max", "count_distinct"])
def test_compile_metric_aggregation_allowlist(layer: SemanticLayer, aggregation: str) -> None:
    """Each supported aggregate is generated from typed metadata only."""
    payload = layer.metrics[0].model_dump()
    payload["measure"]["aggregation"] = aggregation
    card = MetricCard.model_validate({"definition": payload})
    query = compile_metric(card, layer.dimensions, CompileRequest())
    assert (
        "COUNT(DISTINCT" if aggregation == "count_distinct" else aggregation.upper()
    ) in query.sql


@pytest.mark.parametrize(
    ("condition", "fragment"),
    [
        (
            MetricFilter(column="test/main/orders/region", op="in", value=["华东", "华北"]),
            "IN (:p0, :p1)",
        ),
        (MetricFilter(column="test/main/orders/region", op="in", value=[]), "1 = 0"),
        (MetricFilter(column="test/main/orders/region", value=None), "IS NULL"),
        (
            MetricFilter(column="test/main/orders/region", op="ne", value=None),
            'NOT "region" IS NULL',
        ),
    ],
)
def test_compile_metric_membership_and_null_filters(
    layer: SemanticLayer,
    condition: MetricFilter,
    fragment: str,
) -> None:
    """Keep empty membership and null comparisons deterministic across dialects."""
    query = compile_metric(
        MetricCard(definition=layer.metrics[0]),
        layer.dimensions,
        CompileRequest(filters=[condition]),
    )
    assert fragment in query.sql


@pytest.mark.parametrize(
    "compile_request",
    [
        CompileRequest(slices=[DimensionSlice(dimension_id="absent", value="x")]),
        CompileRequest(group_by=["absent"]),
        CompileRequest(filters=[MetricFilter(column="test/main/orders/secret", value=1)]),
    ],
)
def test_compile_metric_unknown_dimension_or_field_is_rejected(
    layer: SemanticLayer,
    compile_request: CompileRequest,
) -> None:
    """Only fields and dimensions registered for this metric may shape SQL."""
    with pytest.raises(ValidationError):
        compile_metric(MetricCard(definition=layer.metrics[0]), layer.dimensions, compile_request)


def test_compile_metric_unresolved_or_invalid_table_is_rejected(layer: SemanticLayer) -> None:
    """Never generate SQL from missing references or malformed stable identities."""
    card = MetricCard(definition=layer.metrics[0], status="unresolved", reasons=["missing field"])
    with pytest.raises(ValidationError, match="unresolved"):
        compile_metric(card, [], CompileRequest())
    metric = layer.metrics[0].model_copy(
        update={"measure": layer.metrics[0].measure.model_copy(update={"table": "bad"})}
    )
    with pytest.raises(ValidationError, match="source/schema/table"):
        compile_metric(MetricCard(definition=metric), [], CompileRequest())


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "UPDATE orders SET amount=0",
        "SELECT 1; SELECT 2",
        "SELECT (",
        "WITH deleted AS (DELETE FROM orders RETURNING *) SELECT * FROM deleted",
        "SELECT * INTO copied FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT 1 UNION SELECT 2",
        "CREATE TABLE evil(x INT)",
    ],
)
def test_select_boundary_rejects_writes_and_multiple_statements(sql: str) -> None:
    """Block data-changing CTEs, SELECT INTO, row locks, and statement chaining."""
    with pytest.raises(ValidationError):
        validate_select(sql, "postgres")


def test_identifier_quoting_preserves_literals_and_rejects_nul() -> None:
    """Field identity is never interpreted as query syntax."""
    assert identifier('bad"; DELETE').sql() == '"bad""; DELETE"'
    for value in ("", "bad\x00"):
        with pytest.raises(ValidationError):
            identifier(value)
    with pytest.raises(ValidationError, match="outside measure table"):
        column_expression("other/column", "table")


def test_encoded_identifier_segments_are_decoded_only_into_quoted_ast(layer: SemanticLayer) -> None:
    """Percent-encoded slash, space, and percent characters remain literal identifiers."""
    measure = layer.metrics[0].measure.model_copy(
        update={
            "table": "source/main/sales%2Fmonthly%20facts",
            "column": "source/main/sales%2Fmonthly%20facts/amount%25",
        }
    )
    metric = layer.metrics[0].model_copy(update={"measure": measure})
    query = compile_metric(MetricCard(definition=metric), [], CompileRequest())
    assert '"sales/monthly facts"' in query.sql
    assert '"amount%"' in query.sql
