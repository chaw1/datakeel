# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed filter AST construction without SQL text interpolation."""

from urllib.parse import unquote

from sqlglot import exp

from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import MetricFilter, ParameterBindings, Scalar

_OPERATORS: dict[str, type[exp.Binary]] = {
    "eq": exp.EQ,
    "ne": exp.NEQ,
    "gte": exp.GTE,
    "lte": exp.LTE,
}


def column_expression(identity: str, table: str) -> exp.Column:
    """Decode one stable field segment and construct a quoted identifier node."""
    if identity.rsplit("/", 1)[0] != table:
        msg = f"Column is outside measure table: {identity}"
        raise ValidationError(msg)
    return exp.Column(this=identifier(identity.rsplit("/", 1)[1]))


def identifier(encoded: str) -> exp.Identifier:
    """Decode catalog escaping once and quote the resulting physical identifier."""
    value = unquote(encoded)
    if not value or "\x00" in value:
        msg = "SQL identifiers must be nonempty and contain no NUL"
        raise ValidationError(msg)
    return exp.to_identifier(value, quoted=True)


def filter_expression(
    condition: MetricFilter, table: str, parameters: ParameterBindings
) -> exp.Expr:
    """Build a comparison AST while adding only named scalar bind parameters."""
    column = column_expression(condition.column, table)
    if isinstance(condition.value, list):
        if not condition.value:
            return exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(0))
        return exp.In(
            this=column, expressions=[bind(value, parameters) for value in condition.value]
        )
    if condition.value is None and condition.op in {"eq", "ne"}:
        condition_ast = exp.Is(this=column, expression=exp.Null())
        return exp.Not(this=condition_ast) if condition.op == "ne" else condition_ast
    return _OPERATORS[condition.op](this=column, expression=bind(condition.value, parameters))


def bind(value: Scalar, parameters: ParameterBindings) -> exp.Var:
    """Append a scalar and expose a portable SQLAlchemy named-bind AST node."""
    name = f"p{len(parameters.values)}"
    parameters.values[name] = value
    return exp.Var(this=f":{name}")
