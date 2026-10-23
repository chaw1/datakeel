# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Construct native day-boundary ASTs after UTC calendar ranges have been resolved."""

from collections.abc import Callable
from typing import Literal

from sqlglot import exp

from datakeel.core.metric_models import ParameterBindings, TimeRange
from datakeel.metrics.compiler_filters import bind

type DateDialect = Literal["sqlite", "postgres"]


def _sqlite_day(parameter: exp.Var) -> exp.Expr:
    return exp.Anonymous(this="DATE", expressions=[parameter])


def _postgres_day(parameter: exp.Var) -> exp.Expr:
    timestamp = exp.Cast(this=parameter, to=exp.DataType(this=exp.DataType.Type.TIMESTAMP))
    return exp.Anonymous(this="DATE_TRUNC", expressions=[exp.Literal.string("day"), timestamp])


# Native functions are selected before serialization; sqlglot performs no date transpilation.
_NATIVE_DAY: dict[DateDialect, Callable[[exp.Var], exp.Expr]] = {
    "sqlite": _sqlite_day,
    "postgres": _postgres_day,
}


def time_predicates(
    column: exp.Column, interval: TimeRange, dialect: DateDialect, parameters: ParameterBindings
) -> tuple[exp.GTE, exp.LT]:
    """Bind typed day boundaries and preserve the inclusive-start, exclusive-end interval."""
    native_day = _NATIVE_DAY[dialect]
    start = native_day(bind(interval.start.isoformat(), parameters))
    end = native_day(bind(interval.end.isoformat(), parameters))
    return exp.GTE(this=column, expression=start), exp.LT(this=column.copy(), expression=end)
