# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate native, deterministic calendar grouping expressions for both SQL dialects."""

from typing import Literal

from sqlglot import exp


def time_group(
    column: exp.Column,
    grain: Literal["day", "month", "quarter", "year"],
    dialect: Literal["sqlite", "postgres"],
) -> exp.Expr:
    """Use ISO date labels so the two backends expose identical result columns and rows."""
    if dialect == "postgres":
        bucket = exp.Anonymous(this="DATE_TRUNC", expressions=[exp.Literal.string(grain), column])
        return exp.Anonymous(this="TO_CHAR", expressions=[bucket, exp.Literal.string("YYYY-MM-DD")])
    formats = {"day": "%Y-%m-%d", "month": "%Y-%m-01", "year": "%Y-01-01"}
    if grain != "quarter":
        return exp.Anonymous(
            this="STRFTIME", expressions=[exp.Literal.string(formats[grain]), column]
        )
    month = exp.Cast(
        this=exp.Anonymous(this="STRFTIME", expressions=[exp.Literal.string("%m"), column]),
        to=exp.DataType(this=exp.DataType.Type.INT),
    )
    offset = exp.Mod(
        this=exp.Paren(this=exp.Sub(this=month, expression=exp.Literal.number(1))),
        expression=exp.Literal.number(3),
    )
    modifier = exp.Anonymous(this="PRINTF", expressions=[exp.Literal.string("-%d months"), offset])
    return exp.Anonymous(
        this="DATE", expressions=[column.copy(), exp.Literal.string("start of month"), modifier]
    )
