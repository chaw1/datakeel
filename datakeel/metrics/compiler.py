# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build canonical SELECT ASTs solely from registered metric definitions."""

from sqlglot import exp

from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import (
    CompiledQuery,
    CompileRequest,
    DimensionDefinition,
    MetricCard,
    MetricDefinition,
    MetricFilter,
    ParameterBindings,
)
from datakeel.metrics.compiler_filters import column_expression, filter_expression, identifier
from datakeel.metrics.date_boundaries import time_predicates
from datakeel.metrics.sql_safety import validate_select

_TABLE_ID_PARTS = 3
_AGGREGATIONS: dict[str, type[exp.AggFunc]] = {
    "sum": exp.Sum,
    "count": exp.Count,
    "avg": exp.Avg,
    "min": exp.Min,
    "max": exp.Max,
}


def compile_metric(
    card: MetricCard, dimensions: list[DimensionDefinition], request: CompileRequest
) -> CompiledQuery:
    """Serialize a canonical AST to SQLite or PostgreSQL without transpiling date math."""
    metric = card.definition
    if card.status != "resolved":
        msg = f"Metric {metric.id} is unresolved: {'; '.join(card.reasons)}"
        raise ValidationError(msg)
    source, schema, table = _table_parts(metric.measure.table)
    allowed = {item.id: item for item in dimensions if item.id in metric.dimensions}
    conditions = _conditions(metric, allowed, request)
    parameters = ParameterBindings()
    predicates = [filter_expression(item, metric.measure.table, parameters) for item in conditions]
    group_columns = [_dimension(allowed, item).column for item in request.group_by]
    groups = [column_expression(item, metric.measure.table) for item in group_columns]
    measure = column_expression(metric.measure.column, metric.measure.table)
    aggregate = (
        exp.Count(this=exp.Distinct(expressions=[measure]))
        if metric.measure.aggregation == "count_distinct"
        else _AGGREGATIONS[metric.measure.aggregation](this=measure)
    )
    columns = {metric.measure.column, *group_columns, *(item.column for item in conditions)}
    if request.time_range:
        time_column = column_expression(metric.time.column, metric.measure.table)
        predicates.extend(
            time_predicates(time_column, request.time_range, request.dialect, parameters)
        )
        columns.add(metric.time.column)
    statement = (
        exp.select(*groups, exp.alias_(aggregate, "value", quoted=True))
        .from_(exp.Table(this=identifier(table), db=identifier(schema)))
        .where(*predicates)
    )
    if groups:
        statement = statement.group_by(*groups).order_by(*groups)
    sql = statement.sql(dialect=request.dialect)
    validate_select(sql, request.dialect)
    return CompiledQuery(
        metric_id=metric.id,
        metric_version=metric.version,
        source_id=source,
        dialect=request.dialect,
        sql=sql,
        parameters=parameters.values,
        tables=[metric.measure.table],
        columns=sorted(columns),
    )


def _conditions(
    metric: MetricDefinition, allowed: dict[str, DimensionDefinition], request: CompileRequest
) -> list[MetricFilter]:
    conditions = [*metric.filters, *request.filters]
    conditions.extend(
        MetricFilter(column=_dimension(allowed, item.dimension_id).column, value=item.value)
        for item in request.slices
    )
    allowed_columns = {
        metric.measure.column,
        metric.time.column,
        *(item.column for item in metric.filters),
        *(item.column for item in allowed.values()),
    }
    if any(item.column not in allowed_columns for item in request.filters):
        msg = "Query filters must reference registered metric fields"
        raise ValidationError(msg)
    return conditions


def _dimension(allowed: dict[str, DimensionDefinition], identity: str) -> DimensionDefinition:
    if identity not in allowed:
        msg = f"Dimension is not registered for this metric: {identity}"
        raise ValidationError(msg)
    return allowed[identity]


def _table_parts(identity: str) -> tuple[str, str, str]:
    parts = identity.split("/")
    if len(parts) != _TABLE_ID_PARTS or not all(parts):
        msg = "Measure table must have source/schema/table identity"
        raise ValidationError(msg)
    return parts[0], parts[1], parts[2]
