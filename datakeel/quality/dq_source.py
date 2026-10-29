# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reuse the semantic query boundary for bounded read-only quality scans."""

from collections.abc import Iterator
from datetime import UTC, datetime
from time import monotonic
from typing import NamedTuple

from sqlglot import exp

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqQueryLimits, DqRule
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metric_models import CompiledQuery, QueryResult, Scalar
from datakeel.core.models import BoundaryModel
from datakeel.metrics.execution import execute_queries, execute_query, stream_query
from datakeel.metrics.sql_safety import validate_select
from datakeel.quality.dq_types import nulls_only

# Side-effect-free built-ins that sqlglot does not model as typed function expressions.
_PURE_FUNCTIONS = {
    "sqlite": frozenset({"datetime", "julianday", "time", "total", "unixepoch"}),
    "postgres": frozenset({"age", "json_typeof", "jsonb_typeof", "make_date"}),
}
_UNIX_EPOCH_JULIAN_DAY = 2440587.5
_ISO_DATE_PREFIX = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*"


def iter_rule_values(
    rule: DqRule, source: SourceProperties, *, reference: bool = False
) -> Iterator[tuple[Scalar, ...]]:
    """Stream an entire column in bounded batches from one read-only database snapshot."""
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
    selection: exp.Expr = exp.column(column, quoted=True) if column else exp.Literal.number(1)
    if column and not reference and nulls_only(rule):
        # NULL checks never fetch values, so JSON, array and binary columns stay evaluable.
        selection = (
            exp.Case().when(selection.is_(exp.null()), exp.null()).else_(exp.Literal.number(1))
        )
    query = exp.select(selection).from_(exp.table_(table, db=schema, quoted=True))
    compiled = compile_rule_query(rule, source, query.sql(dialect=source_dialect(source)))
    for batch in stream_query(
        source.connection_url or "",
        compiled,
        DqQueryLimits(timeout_ms=rule.timeout_ms, max_rows=rule.max_rows),
    ):
        yield tuple(row[0] for row in batch.rows)


class TableAggregate(NamedTuple):
    """Database-side totals: row count, newest valid timestamp and unparsable timestamp cells."""

    row_count: int
    latest: datetime | None = None
    invalid: int = 0


def read_table_aggregate(rule: DqRule, source: SourceProperties) -> TableAggregate:
    """Push COUNT/MAX into one bounded read-only statement, so table size has no row cap."""
    dialect = source_dialect(source)
    table = exp.table_(rule.target.table, db=rule.target.schema_name, quoted=True)
    count = exp.Count(this=exp.Star())
    if rule.kind != "freshness" or not rule.target.column:
        row = _single_row(rule, source, exp.select(count).from_(table).sql(dialect=dialect))
        return TableAggregate(whole_number(row[0]))
    column = exp.column(rule.target.column, quoted=True)
    if dialect == "postgres":
        # DATE/TIMESTAMP columns only; +/-infinity is not a usable delivery time.
        valid = exp.Anonymous(this="isfinite", expressions=[column.copy()])
        latest_value = exp.Case().when(valid, column.copy())
    else:
        # SQLite stores timestamps as text; julianday() honours offsets and rejects malformed
        # text, while the GLOB keeps 'now' or bare Julian numbers from counting as timestamps.
        valid = exp.and_(
            exp.EQ(this=exp.Typeof(this=column.copy()), expression=exp.Literal.string("text")),
            exp.Glob(this=column.copy(), expression=exp.Literal.string(_ISO_DATE_PREFIX)),
        )
        latest_value = exp.Case().when(
            valid, exp.Anonymous(this="julianday", expressions=[column.copy()])
        )
    invalid = (
        exp.Case()
        .when(
            exp.and_(exp.not_(column.copy().is_(exp.null())), latest_value.copy().is_(exp.null())),
            exp.Literal.number(1),
        )
        .else_(exp.Literal.number(0))
    )
    query = exp.select(count, exp.Max(this=latest_value), exp.Sum(this=invalid)).from_(table)
    row = _single_row(rule, source, query.sql(dialect=dialect))
    return TableAggregate(whole_number(row[0]), _latest(row[1], dialect), whole_number(row[2]))


def _single_row(rule: DqRule, source: SourceProperties, sql: str) -> list[Scalar]:
    result = execute_rule_query(rule, source, sql)
    if len(result.rows) != 1:
        msg = "Quality aggregate did not return exactly one row"
        raise ExecutionError(msg)
    return result.rows[0]


def whole_number(value: Scalar) -> int:
    """Read an aggregate count, treating SQL NULL as zero."""
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _latest(value: Scalar, dialect: str) -> datetime | None:
    if dialect == "sqlite":
        if not isinstance(value, int | float) or isinstance(value, bool):
            return None
        # Julian-day doubles carry ~40 µs of error; SQLite itself keeps millisecond precision.
        seconds = round((float(value) - _UNIX_EPOCH_JULIAN_DAY) * 86400, 3)
        return datetime.fromtimestamp(seconds, UTC)
    if not isinstance(value, str):
        return None
    # The driver value arrives as ISO text; naive PostgreSQL timestamps are stored as UTC.
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp


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
    parsed = validate_select(sql, source_dialect(source))
    _reject_unsafe_calls(parsed, source_dialect(source))
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
        dialect=source_dialect(source)
    )
    # Rewrite only parsed identifier spans: original named binds and all other SQL stay intact.
    spans = sorted({_table_span(table, len(sql)) for table in tables}, reverse=True)
    for start, end in spans:
        sql = sql[:start] + identity + sql[end + 1 :]
    validate_select(sql, source_dialect(source))
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


class AssertionObservation(BoundaryModel):
    """Pair bounded assertion violations with the target count from the same source snapshot."""

    result: QueryResult
    rows_total: int


def execute_assertion(rule: DqRule, source: SourceProperties) -> AssertionObservation:
    """Run an assertion without preflight, retaining only bounded violations and coverage."""
    started = monotonic()
    sql = _assertion_sql(rule, source)
    total_sql = (
        exp.select(exp.Count(this=exp.Star()))
        .from_(exp.table_(rule.target.table, db=rule.target.schema_name, quoted=True))
        .sql(dialect=source_dialect(source))
    )
    timeout_ms = rule.timeout_ms - int((monotonic() - started) * 1000)
    if timeout_ms < 1:
        msg = "Quality assertion exceeded its execution timeout"
        raise ExecutionError(msg)
    result, total = execute_queries(
        source.connection_url or "",
        (
            compile_rule_query(rule, source, sql, rule.params.bindings),
            compile_rule_query(rule, source, total_sql),
        ),
        DqQueryLimits(timeout_ms=timeout_ms, max_rows=rule.max_rows),
    )
    if result.truncated:
        msg = "Quality assertion result row limit exceeded"
        raise ExecutionError(msg)
    return AssertionObservation(result=result, rows_total=whole_number(total.rows[0][0]))


def source_dialect(source: SourceProperties) -> str:
    """Normalize the registered source dialect for SQL compilation."""
    return "postgres" if source.dialect in {"postgres", "postgresql"} else "sqlite"


def execute_rule_query(
    rule: DqRule, source: SourceProperties, sql: str, bindings: dict[str, Scalar] | None = None
) -> QueryResult:
    """Execute a bounded result query through the shared read-only boundary."""
    return execute_query(
        source.connection_url or "",
        compile_rule_query(rule, source, sql, bindings),
        DqQueryLimits(timeout_ms=rule.timeout_ms, max_rows=rule.max_rows),
    )


def compile_rule_query(
    rule: DqRule, source: SourceProperties, sql: str, bindings: dict[str, Scalar] | None = None
) -> CompiledQuery:
    """Bind a quality query to a supported registered source and frozen rule identity."""
    if not source.connection_url or source.dialect not in {"sqlite", "postgres", "postgresql"}:
        msg = "Quality execution requires a supported registered business source"
        raise ValidationError(msg)
    return CompiledQuery(
        metric_id=rule.id,
        metric_version=rule.revision,
        source_id=rule.target.source_id,
        dialect="postgres" if source_dialect(source) == "postgres" else "sqlite",
        sql=sql,
        parameters=bindings or {},
        tables=[rule.target.table],
        columns=[rule.target.column] if rule.target.column else [],
    )
