# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reuse the semantic query boundary for bounded read-only quality scans."""

from time import monotonic

from sqlglot import exp

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqQueryLimits, DqRule
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metric_models import CompiledQuery, QueryResult, Scalar
from datakeel.metrics.execution import execute_query
from datakeel.metrics.sql_safety import validate_select

# Side-effect-free built-ins that sqlglot does not model as typed function expressions.
_PURE_FUNCTIONS = {
    "sqlite": frozenset({"datetime", "julianday", "time", "total", "unixepoch"}),
    "postgres": frozenset({"age", "json_typeof", "jsonb_typeof", "make_date"}),
}


def read_rule_table(
    rule: DqRule, source: SourceProperties, *, reference: bool = False
) -> QueryResult:
    """Scan at most the declared cap plus one sentinel row and refuse partial verdicts."""
    table = rule.params.reference_table if reference else rule.target.table
    column = rule.params.reference_column if reference else rule.target.column
    schema = (
        rule.params.reference_schema or rule.target.schema_name
        if reference
        else rule.target.schema_name
    )
    if not table:
        msg = "A reference table is required"
        raise ValidationError(msg)
    selection = exp.column(column, quoted=True) if column else exp.Literal.number(1)
    query = exp.select(selection).from_(exp.table_(table, db=schema, quoted=True))
    query = query.limit(rule.max_rows + 1)
    result = _execute(rule, source, query.sql(dialect=_dialect(source)))
    if result.truncated:
        msg = "Quality rule scan row limit exceeded; no partial verdict was produced"
        raise ExecutionError(msg)
    return result


def validate_assertion(rule: DqRule, source: SourceProperties) -> None:
    """Reject unsafe assertion SQL and undeclared scan scope without opening a connection."""
    _assertion_sql(rule, source)


def _reject_unsafe_calls(parsed: exp.Select, dialect: str) -> None:
    # Read-only transactions still allow calls such as pg_terminate_backend or query_to_xml,
    # so assertions may only use functions sqlglot recognises plus a few pure date helpers.
    for node in parsed.walk():
        if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
            msg = "SQL assertions cannot call schema-qualified functions"
            raise ValidationError(msg)
        if isinstance(node, exp.Anonymous) and node.name.lower() not in _PURE_FUNCTIONS[dialect]:
            msg = f"SQL assertions may only call built-in read-only functions, not {node.name}"
            raise ValidationError(msg)


def _assertion_sql(rule: DqRule, source: SourceProperties) -> str:
    sql = rule.params.sql or ""
    parsed = validate_select(sql, _dialect(source))
    _reject_unsafe_calls(parsed, _dialect(source))
    tables = tuple(parsed.find_all(exp.Table))
    if any(
        table.catalog
        or table.name != rule.target.table
        or (table.db and table.db != rule.target.schema_name)
        for table in tables
    ):
        msg = "SQL assertions may read only their declared target table"
        raise ValidationError(msg)
    if parsed.find(exp.With) is not None:
        msg = "SQL assertions do not permit recursive or derived CTE scans"
        raise ValidationError(msg)
    identity = exp.table_(rule.target.table, db=rule.target.schema_name, quoted=True).sql(
        dialect=_dialect(source)
    )
    # Rewrite only parsed identifier spans: original named binds and all other SQL stay intact.
    spans = sorted({_table_span(table, len(sql)) for table in tables}, reverse=True)
    for start, end in spans:
        sql = sql[:start] + identity + sql[end + 1 :]
    validate_select(sql, _dialect(source))
    return sql


def _table_span(table: exp.Table, length: int) -> tuple[int, int]:
    parts = table.parts
    if not parts or any(not isinstance(part, exp.Identifier) for part in parts):
        msg = "SQL assertions require literal target table identifiers"
        raise ValidationError(msg)
    start, end = parts[0].meta.get("start"), parts[-1].meta.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end < length:
        msg = "SQL assertion target positions cannot be resolved safely"
        raise ValidationError(msg)
    return start, end


def execute_assertion(rule: DqRule, source: SourceProperties) -> QueryResult:
    """Return assertion violations after verifying source scope and row bounds."""
    started = monotonic()
    sql = _assertion_sql(rule, source)
    read_rule_table(rule, source)
    timeout_ms = rule.timeout_ms - int((monotonic() - started) * 1000)
    if timeout_ms < 1:
        msg = "Quality assertion exceeded its execution timeout"
        raise ExecutionError(msg)
    result = _execute(
        rule.model_copy(update={"timeout_ms": timeout_ms}), source, sql, rule.params.bindings
    )
    if result.truncated:
        msg = "Quality assertion result row limit exceeded"
        raise ExecutionError(msg)
    return result


def _dialect(source: SourceProperties) -> str:
    return "postgres" if source.dialect in {"postgres", "postgresql"} else "sqlite"


def _execute(
    rule: DqRule, source: SourceProperties, sql: str, bindings: dict[str, Scalar] | None = None
) -> QueryResult:
    if not source.connection_url or source.dialect not in {"sqlite", "postgres", "postgresql"}:
        msg = "Quality execution requires a supported registered business source"
        raise ValidationError(msg)
    query = CompiledQuery(
        metric_id=rule.id,
        metric_version=rule.revision,
        source_id=rule.target.source_id,
        dialect="postgres" if _dialect(source) == "postgres" else "sqlite",
        sql=sql,
        parameters=bindings or {},
        tables=[rule.target.table],
        columns=[rule.target.column] if rule.target.column else [],
    )
    return execute_query(
        source.connection_url,
        query,
        DqQueryLimits(timeout_ms=rule.timeout_ms, max_rows=rule.max_rows),
    )
