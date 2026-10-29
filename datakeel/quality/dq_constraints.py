# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Database-side constraint counts without transferring rows or reference sets."""

import math

from sqlglot import exp

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqRule
from datakeel.core.metric_models import Scalar
from datakeel.core.models import BoundaryModel
from datakeel.quality.dq_source import execute_rule_query, source_dialect, whole_number


class ConstraintCounts(BoundaryModel):
    """Keep only exact totals and one redacted failure ordinal from a database scan."""

    rows: int
    failed: int
    nulls: int
    first_failure: int | None = None
    mean: float | None = None
    stddev: float | None = None


def count_constraints(rule: DqRule, source: SourceProperties) -> ConstraintCounts:
    """Evaluate every target row in one aggregate, with database-side duplicate grouping."""
    column = exp.column(rule.target.column or "", table="dq_target", quoted=True)
    table = exp.table_(rule.target.table, db=rule.target.schema_name, quoted=True).as_("dq_target")
    query = exp.select(
        column.as_("dq_value"), exp.Window(this=exp.RowNumber()).as_("dq_ordinal")
    ).from_(table)
    if rule.kind == "unique":
        query = query.select(
            exp.Window(
                this=exp.Count(this=exp.Star()), partition_by=[_json_value(column.copy(), source)]
            ).as_("dq_copies")
        )
    predicate = _predicate(rule, source, exp.column("dq_value", table="dq_rows", quoted=True))
    marker = exp.Case().when(predicate.copy(), exp.Literal.number(1)).else_(exp.Literal.number(0))
    null_marker = exp.Case().when(exp.column("dq_value").is_(exp.null()), 1).else_(0)
    first = exp.Case().when(predicate, exp.column("dq_ordinal"))
    selections: list[exp.Expr] = [
        exp.Count(this=exp.Star()),
        exp.Sum(this=marker),
        exp.Sum(this=null_marker),
        exp.Min(this=first),
    ]
    if rule.kind != "not_null":
        query, moments = _moments(query, source)
        selections.extend(moments)
    aggregate = exp.select(*selections).from_(query.subquery("dq_rows"))
    if rule.params.reference_table:
        aggregate = aggregate.join(
            _reference_keys(rule, source).subquery("dq_reference"),
            on=exp.EQ(
                this=_json_value(exp.column("dq_value", table="dq_rows", quoted=True), source),
                expression=exp.column("dq_key", table="dq_reference", quoted=True),
            ),
            join_type="LEFT",
        )
    row = execute_rule_query(rule, source, aggregate.sql(dialect=source_dialect(source))).rows[0]
    return ConstraintCounts(
        rows=whole_number(row[0]),
        failed=whole_number(row[1]),
        nulls=whole_number(row[2]),
        first_failure=whole_number(row[3]) if row[3] is not None else None,
        mean=float(row[4]) if rule.kind != "not_null" and row[4] is not None else None,
        stddev=math.sqrt(max(0, float(row[5]))) * float(row[6])
        if rule.kind != "not_null" and row[5] is not None and row[6] is not None
        else None,
    )


def _predicate(rule: DqRule, source: SourceProperties, column: exp.Column) -> exp.Expr:
    if rule.kind == "not_null":
        return column.is_(exp.null())
    if rule.kind == "unique":
        invalid = exp.GT(this=exp.column("dq_copies"), expression=exp.Literal.number(1))
    elif rule.kind == "range":
        invalid = _range(rule, source, column)
    else:
        invalid = _membership(rule, source, column)
    return exp.and_(exp.not_(column.copy().is_(exp.null())), invalid)


def _json_value(value: exp.Expr, source: SourceProperties) -> exp.Expr:
    # PostgreSQL JSONB equality preserves numeric equality and compares UUID/text as text,
    # without incompatible UUID = TEXT operators or loading the reference table in Python.
    return (
        exp.Anonymous(this="to_jsonb", expressions=[value])
        if source_dialect(source) == "postgres"
        else exp.Case().when(exp.true(), value)
    )


def _membership(rule: DqRule, source: SourceProperties, column: exp.Column) -> exp.Expr:
    value = _json_value(column.copy(), source)
    if rule.params.reference_table:
        return exp.column("dq_key", table="dq_reference", quoted=True).is_(exp.null())
    allowed = tuple(item for item in rule.params.values if item is not None)
    if not allowed:
        return exp.true()
    return exp.not_(value.isin(*(_json_value(_literal(item), source) for item in allowed)))


def _literal(value: Scalar) -> exp.Expr:
    expression = exp.convert(value)
    # PostgreSQL polymorphic to_jsonb() cannot infer the type of an unknown string literal.
    return exp.cast(expression, "TEXT") if isinstance(value, str) else expression


def _range(rule: DqRule, source: SourceProperties, column: exp.Column) -> exp.Expr:
    conditions: list[exp.Expr] = []
    if source_dialect(source) == "sqlite":
        conditions.append(exp.not_(exp.Typeof(this=column.copy()).isin("integer", "real")))
        conditions.append(
            exp.GT(
                this=exp.Abs(this=exp.cast(column.copy(), "DOUBLE")),
                expression=exp.Literal.number("1.7976931348623157e308"),
            )
        )
    else:
        # Infinity and NaN must fail even a one-sided bound.
        conditions.append(exp.cast(column.copy(), "TEXT").isin("Infinity", "-Infinity", "NaN"))
    if rule.params.minimum is not None:
        conditions.append(exp.LT(this=column.copy(), expression=exp.convert(rule.params.minimum)))
    if rule.params.maximum is not None:
        conditions.append(exp.GT(this=column.copy(), expression=exp.convert(rule.params.maximum)))
    return exp.or_(*conditions)


def _numeric_value(source: SourceProperties) -> exp.Expr:
    column = exp.column("dq_value", quoted=True)
    if source_dialect(source) == "sqlite":
        valid = exp.Typeof(this=column.copy()).isin("integer", "real")
        numeric = exp.cast(column.copy(), "DOUBLE")
    else:
        type_name = exp.cast(exp.Anonymous(this="pg_typeof", expressions=[column.copy()]), "TEXT")
        valid = type_name.isin(
            "smallint", "integer", "bigint", "numeric", "real", "double precision"
        )
        magnitude = exp.Abs(this=exp.cast(exp.cast(column.copy(), "TEXT"), "NUMERIC"))
        representable = exp.LTE(
            this=magnitude, expression=exp.Literal.number("1.7976931348623157e308")
        )
        numeric = exp.Case().when(
            representable, exp.cast(exp.cast(column.copy(), "TEXT"), "DOUBLE PRECISION")
        )
    finite = exp.not_(
        exp.cast(column.copy(), "TEXT").isin("Infinity", "-Infinity", "NaN", "Inf", "-Inf")
    )
    return exp.Case().when(exp.and_(valid, finite), numeric)


def _moments(query: exp.Select, source: SourceProperties) -> tuple[exp.Select, list[exp.Expr]]:
    # Scale before averaging/squaring, preserving finite values such as 1e308 without overflow.
    numbers = (
        exp.select("*")
        .select(_numeric_value(source).as_("dq_number"))
        .from_(query.subquery("dq_numbers"))
    )
    number = exp.column("dq_number")
    scale = exp.Window(this=exp.Max(this=exp.Abs(this=number.copy())))
    scaled = exp.Coalesce(
        this=exp.Div(
            this=number.copy(),
            expression=exp.Nullif(this=scale.copy(), expression=exp.Literal.number(0)),
        ),
        expressions=[
            exp.Case().when(exp.not_(number.copy().is_(exp.null())), exp.Literal.number(0))
        ],
    )
    normal = (
        exp.select("*")
        .select(scale.as_("dq_scale"), scaled.as_("dq_scaled"))
        .from_(numbers.subquery("dq_normal"))
    )
    mean = exp.Window(this=exp.Avg(this=exp.column("dq_scaled")))
    centered = exp.select("*").select(mean.as_("dq_mean")).from_(normal.subquery("dq_centered"))
    delta = exp.Sub(this=exp.column("dq_scaled"), expression=exp.column("dq_mean"))
    return centered, [
        exp.Mul(
            this=exp.Avg(this=exp.column("dq_scaled")),
            expression=exp.Max(this=exp.column("dq_scale")),
        ),
        exp.Avg(
            this=exp.Mul(this=exp.Paren(this=delta.copy()), expression=exp.Paren(this=delta.copy()))
        ),
        exp.Max(this=exp.column("dq_scale")),
    ]


def _reference_keys(rule: DqRule, source: SourceProperties) -> exp.Select:
    reference = exp.table_(
        rule.params.reference_table or "",
        db=rule.params.reference_schema or rule.target.schema_name,
        quoted=True,
    )
    key = exp.column(rule.params.reference_column or "", quoted=True)
    return (
        exp.select(_json_value(key.copy(), source).as_("dq_key"))
        .distinct()
        .from_(reference)
        .where(exp.not_(key.is_(exp.null())))
    )
