# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse every execution statement and reject anything outside read-only SELECT."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.expressions.dml import DML

from datakeel.core.errors import ValidationError


def validate_select(sql: str, dialect: str = "sqlite") -> exp.Select:
    """Accept exactly one SELECT without write subqueries, locks, or INTO targets."""
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except ParseError as exc:
        msg = "Invalid SELECT SQL"
        raise ValidationError(msg) from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        msg = "Only one SELECT statement is permitted"
        raise ValidationError(msg)
    statement = statements[0]
    forbidden = (DML, exp.DDL, exp.Command, exp.Into, exp.Lock)
    if any(isinstance(node, forbidden) for node in statement.walk()):
        msg = "SELECT cannot contain writes, INTO, or row locks"
        raise ValidationError(msg)
    return statement
