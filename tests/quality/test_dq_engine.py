# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local business fixtures exercise every rule without external services."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import text
from sqlglot import exp

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqKind, DqParameters, DqResult, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import QueryResult, Scalar
from datakeel.quality.dq_engine import execute_rule
from datakeel.storage.database import Database

NOW = datetime(2026, 10, 27, 9, tzinfo=UTC)


def business_source(
    folder: Path, values: tuple[Scalar, ...], reference: tuple[Scalar, ...] = ()
) -> SourceProperties:
    """Generate an isolated SQLite business source with an optional code table."""
    path = folder / "quality-source.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations(value)")
        connection.execute("CREATE TABLE codes(code)")
        connection.executemany(
            "INSERT INTO observations VALUES (?)", [(value,) for value in values]
        )
        connection.executemany("INSERT INTO codes VALUES (?)", [(value,) for value in reference])
    return SourceProperties(connection_url=f"sqlite:///{path}", dialect="sqlite")


def rule_of(kind: DqKind, params: DqParameters | None = None, threshold: float = 0) -> DqRule:
    """Construct a representative column rule for the generated fixture."""
    return DqRule(
        id="rule",
        name="Generated quality rule",
        kind=kind,
        target=DqTarget(source_id="demo", table="observations", column="value"),
        params=params or DqParameters(),
        threshold=threshold,
        owner="quality-team",
    )


@pytest.mark.parametrize(
    ("kind", "params", "good", "bad"),
    [
        ("not_null", DqParameters(), (1, 2), (1, None)),
        ("unique", DqParameters(), (1, 2), (1, 1)),
        ("range", DqParameters(minimum=0, maximum=10), (0, 10), (-1, 11)),
        (
            "accepted_values",
            DqParameters(values=("active", "pending")),
            ("active", "pending"),
            ("active", "unknown"),
        ),
        ("regex", DqParameters(pattern="^[A-Z]{2}$"), ("AB", "CD"), ("AB", "invalid")),
        (
            "referential_integrity",
            DqParameters(reference_table="codes", reference_column="code"),
            (1, 2),
            (1, 99),
        ),
        ("freshness", DqParameters(), ("2026-10-27T08:59:59Z",), ("2026-10-20T08:00:00Z",)),
        (
            "sql_assertion",
            DqParameters(
                sql="SELECT value FROM observations WHERE value < :floor", bindings={"floor": 0}
            ),
            (1, 2),
            (1, -1),
        ),
    ],
)
def test_every_row_rule_accepts_good_and_rejects_bad(
    tmp_path: Path,
    kind: DqKind,
    params: DqParameters,
    good: tuple[Scalar, ...],
    bad: tuple[Scalar, ...],
) -> None:
    """Each independent rule type has a positive and a deliberately violated case."""
    threshold = 60 if kind == "freshness" else 0
    rule = rule_of(kind, params, threshold)
    good_folder, bad_folder = tmp_path / "good", tmp_path / "bad"
    good_folder.mkdir()
    bad_folder.mkdir()
    assert execute_rule(rule, business_source(good_folder, good, (1, 2)), now=NOW).passed is True
    result = execute_rule(rule, business_source(bad_folder, bad, (1, 2)), now=NOW)
    assert result.passed is False
    assert "invalid" not in result.model_dump_json()
    assert all(sample.value == "[REDACTED]" for sample in result.samples)


def history_for(rule: DqRule, values: tuple[Scalar, ...], folder: Path) -> tuple[DqResult, ...]:
    """Collect real cold-start observations that bootstrap the baseline safely."""
    source = business_source(folder, values)
    history: tuple[DqResult, ...] = ()
    for index in range(rule.params.baseline_runs):
        result = execute_rule(rule, source, history, NOW - timedelta(days=4 - index))
        assert result.status == "baseline_insufficient"
        history += (result,)
    return history


@pytest.mark.parametrize(
    ("kind", "params", "baseline", "good", "bad"),
    [
        ("volume_change", DqParameters(), (1, 2, 3, 4), (1, 2, 3, 4), (1,)),
        ("distribution_drift", DqParameters(statistic="mean"), (10, 10), (9, 11), (100, 100)),
        ("distribution_drift", DqParameters(statistic="stddev"), (1, 3), (2, 4), (1, 100)),
        (
            "distribution_drift",
            DqParameters(statistic="null_rate"),
            (1, None),
            (2, None),
            (None, None),
        ),
        (
            "distribution_drift",
            DqParameters(statistic="psi", bin_edges=(5, 15)),
            (1, 10, 20),
            (2, 11, 21),
            (100, 101, 102),
        ),
    ],
)
def test_historical_rules_bootstrap_compare_and_detect_drift(
    tmp_path: Path,
    kind: DqKind,
    params: DqParameters,
    baseline: tuple[Scalar, ...],
    good: tuple[Scalar, ...],
    bad: tuple[Scalar, ...],
) -> None:
    """Volume and all four distribution statistics use measured historical baselines."""
    folders = tuple(tmp_path / name for name in ("baseline", "good", "bad"))
    for folder in folders:
        folder.mkdir()
    rule = rule_of(kind, params, 0.5)
    history = history_for(rule, baseline, folders[0])
    assert execute_rule(rule, business_source(folders[1], good), history, NOW).passed is True
    assert execute_rule(rule, business_source(folders[2], bad), history, NOW).passed is False


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM observations",
        "SELECT 1; SELECT 2",
        "SELECT * INTO copied FROM observations",
        "SELECT * FROM observations FOR UPDATE",
        "SELECT * FROM codes",
        "SELECT * FROM other.observations",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "WITH x AS (SELECT 1) SELECT * FROM observations",
        "SELECT * FROM (DELETE FROM observations)",
        "SELECT (",
    ],
)
def test_sql_assertions_reject_unsafe_or_out_of_scope_sql(tmp_path: Path, sql: str) -> None:
    """Writes, multiple statements, locks, CTEs and undeclared tables fail before execution."""
    source = business_source(tmp_path, (1,))
    result = execute_rule(rule_of("sql_assertion", DqParameters(sql=sql)), source, now=NOW)
    assert result.status == "error"
    with sqlite3.connect(tmp_path / "quality-source.sqlite") as connection:
        assert connection.execute("SELECT count(*) FROM observations").fetchone()[0] == 1


def test_sql_assertion_bindings_are_literals(tmp_path: Path) -> None:
    """Injection-looking parameter content cannot alter SQL assertion structure."""
    value = "x' OR 1=1 --"
    source = business_source(tmp_path, (value, "plain"))
    rule = rule_of(
        "sql_assertion",
        DqParameters(
            sql="SELECT value FROM observations WHERE value = :needle", bindings={"needle": value}
        ),
    )
    result = execute_rule(rule, source, now=NOW)
    assert result.failed_count == 1
    assert value not in result.model_dump_json()


def test_scan_row_cap_refuses_partial_success(tmp_path: Path) -> None:
    """A violation past the cap cannot become an apparently passing partial scan."""
    source = business_source(tmp_path, (1, 2, None))
    rule = rule_of("not_null").model_copy(update={"max_rows": 2})
    result = execute_rule(rule, source, now=NOW)
    assert result.status == "error"
    assert "scan row limit" in result.message


def test_sql_assertion_preflight_caps_source_not_just_output(tmp_path: Path) -> None:
    """A one-row aggregate cannot conceal an oversized target source scan."""
    source = business_source(tmp_path, tuple(range(11)))
    rule = rule_of("sql_assertion", DqParameters(sql="SELECT count(*) FROM observations"))
    assert execute_rule(rule.model_copy(update={"max_rows": 10}), source).status == "error"


def test_database_enforces_sql_timeout(tmp_path: Path) -> None:
    """The reused SQLite VM deadline interrupts an expensive read-only cross join."""
    source = business_source(tmp_path, tuple(range(100)))
    sql = (
        "SELECT sum(a.value*b.value*c.value*d.value) FROM observations a "
        "CROSS JOIN observations b CROSS JOIN observations c CROSS JOIN observations d"
    )
    rule = rule_of("sql_assertion", DqParameters(sql=sql)).model_copy(update={"timeout_ms": 1})
    assert execute_rule(rule, source).status == "error"


@pytest.mark.parametrize(
    "kind", ["unique", "range", "accepted_values", "regex", "referential_integrity"]
)
def test_nulls_are_delegated_to_explicit_not_null_rule(tmp_path: Path, kind: DqKind) -> None:
    """SQL-style nullable columns use a separate rule to prohibit absent values."""
    params = DqParameters(
        minimum=0, values=(1,), pattern="x", reference_table="codes", reference_column="code"
    )
    result = execute_rule(rule_of(kind, params), business_source(tmp_path, (None, None)), now=NOW)
    assert result.status == "passed"


def test_accepted_values_can_reference_code_table(tmp_path: Path) -> None:
    """An explicit code table is consulted through the same bounded read-only connection."""
    rule = rule_of(
        "accepted_values", DqParameters(reference_table="codes", reference_column="code")
    )
    result = execute_rule(rule, business_source(tmp_path, ("A", "B"), ("A",)), now=NOW)
    assert result.failed_count == 1


@pytest.mark.parametrize("values", [(), (None,), ("invalid",), (123,)])
def test_freshness_without_valid_timestamps_fails(
    tmp_path: Path, values: tuple[Scalar, ...]
) -> None:
    """Empty or malformed timestamp columns cannot falsely appear fresh."""
    assert (
        execute_rule(rule_of("freshness"), business_source(tmp_path, values), now=NOW).passed
        is False
    )


def test_freshness_accepts_naive_utc_storage_and_ignores_null(tmp_path: Path) -> None:
    """Naive SQL timestamp values are explicitly interpreted in UTC."""
    source = business_source(tmp_path, (None, "2026-10-27T09:00:00"))
    assert execute_rule(rule_of("freshness"), source, now=NOW).actual_value == 0


def test_execution_rejects_naive_injected_clock(tmp_path: Path) -> None:
    """Callers must inject an aware instant rather than local-wall-clock ambiguity."""
    with pytest.raises(ValidationError, match="aware"):
        execute_rule(
            rule_of("not_null"), business_source(tmp_path, (1,)), now=NOW.replace(tzinfo=None)
        )


def test_unregistered_source_is_an_explicit_error() -> None:
    """Missing connection configuration never opens another database as a fallback."""
    result = execute_rule(rule_of("not_null"), SourceProperties(dialect="sqlite"), now=NOW)
    assert result.status == "error"


def test_distribution_non_numeric_history_fails_explicitly(tmp_path: Path) -> None:
    """Unavailable numeric metrics are distinct from an ordinary failed comparison."""
    rule = rule_of("distribution_drift", DqParameters(baseline_runs=1))
    source = business_source(tmp_path, ("text",))
    previous = execute_rule(rule, source, now=NOW - timedelta(days=1))
    assert execute_rule(rule, source, (previous,), NOW).status == "error"


def test_historical_baselines_exclude_failures_other_revisions_and_future(tmp_path: Path) -> None:
    """Only successful prior observations from this exact rule revision count."""
    rule = rule_of("volume_change", DqParameters(baseline_runs=1))
    source = business_source(tmp_path, (1, 2))
    previous = execute_rule(rule, source, now=NOW - timedelta(days=1))
    history = (
        previous.model_copy(update={"status": "failed"}),
        previous.model_copy(update={"rule_revision": 2}),
        previous.model_copy(update={"started_at": NOW + timedelta(days=1)}),
        previous.model_copy(update={"rule_id": "other"}),
    )
    assert execute_rule(rule, source, history, NOW).status == "baseline_insufficient"


def test_regex_backtracking_is_terminated_without_stalling_worker(tmp_path: Path) -> None:
    """A syntactically valid catastrophic expression respects the whole rule deadline."""
    source = business_source(tmp_path, ("a" * 100 + "!",))
    rule = rule_of("regex", DqParameters(pattern="(a+)+$")).model_copy(update={"timeout_ms": 100})
    assert execute_rule(rule, source, now=NOW).status == "error"
    assert execute_rule(rule_of("not_null"), source, now=NOW).passed is True


def test_long_regex_cells_are_not_silently_truncated(tmp_path: Path) -> None:
    """Matching uses the full cell so a violation beyond a prefix is still reported."""
    source = business_source(tmp_path, ("a" * 10001 + "!",))
    assert (
        execute_rule(rule_of("regex", DqParameters(pattern="a+")), source, now=NOW).passed is False
    )


def test_psi_rejects_changed_histogram_bins(tmp_path: Path) -> None:
    """Historical bins cannot be silently paired by position after configuration changes."""
    params = DqParameters(statistic="psi", baseline_runs=1, bin_edges=(0, 5))
    rule = rule_of("distribution_drift", params)
    source = business_source(tmp_path, (1, 2))
    old = execute_rule(rule, source, now=NOW - timedelta(days=1))
    old = old.model_copy(update={"metrics": old.metrics.model_copy(update={"bin_edges": (1, 3)})})
    assert execute_rule(rule, source, (old,), NOW).status == "error"


@pytest.mark.parametrize("value", ["text"])
def test_range_non_numeric_values_fail(tmp_path: Path, value: Scalar) -> None:
    """Wrongly typed numeric data does not silently disappear from the violation ratio."""
    assert (
        execute_rule(
            rule_of("range", DqParameters(minimum=0)), business_source(tmp_path, (value,)), now=NOW
        ).passed
        is False
    )


def test_native_database_rules_use_existing_read_only_executor(db: Database) -> None:
    """Both database matrix stacks execute native typed values, binds and schema quoting."""
    with db.engine.begin() as connection:
        schema = (
            None
            if db.sqlite
            else str(connection.execute(text("SELECT current_schema()")).scalar_one())
        )
        connection.execute(text("CREATE TABLE dq_native_values(value INTEGER, stamp TIMESTAMP)"))
        connection.execute(text("INSERT INTO dq_native_values VALUES (2, '2026-10-27 09:00:00')"))
    source = SourceProperties(
        connection_url=db.engine.url.render_as_string(hide_password=False),
        dialect=db.engine.dialect.name,
    )
    target = DqTarget(
        source_id="demo", schema_name=schema, table="dq_native_values", column="value"
    )
    rule = DqRule(
        id="native",
        name="Native values",
        owner="quality-team",
        target=target,
        kind="range",
        params=DqParameters(minimum=0, maximum=3),
    )
    assert execute_rule(rule, source, now=NOW).passed is True
    table = exp.table_("dq_native_values", db=schema, quoted=True)
    sql = exp.select("value").from_(table).where("value < :floor").sql()
    assertion = rule.model_copy(
        update={"kind": "sql_assertion", "params": DqParameters(sql=sql, bindings={"floor": 0})}
    )
    assert execute_rule(assertion, source, now=NOW).passed is True
    timestamp_rule = rule.model_copy(
        update={
            "kind": "freshness",
            "params": DqParameters(),
            "target": target.model_copy(update={"column": "stamp"}),
        }
    )
    assert execute_rule(timestamp_rule, source, now=NOW).actual_value == 0
    for statistic in ("mean", "stddev", "psi"):
        numeric_rule = rule.model_copy(
            update={
                "kind": "distribution_drift",
                "params": DqParameters(statistic=statistic, baseline_runs=1),
            }
        )
        cold = execute_rule(numeric_rule, source, now=NOW - timedelta(days=1))
        assert execute_rule(numeric_rule, source, (cold,), NOW).status == "passed"


def test_not_null_guard_reports_missing_business_values(tmp_path: Path) -> None:
    """The required-value verdict must be computed from real missing database cells."""
    result = execute_rule(rule_of("not_null"), business_source(tmp_path, (1, None)), now=NOW)
    assert result.status == "failed"
    assert result.actual_value == 0.5


def test_baseline_insufficient_observations_can_warm_start(tmp_path: Path) -> None:
    """A cold-start observation supplies baseline evidence to a later successful run."""
    rule = rule_of("volume_change", DqParameters(baseline_runs=1))
    source = business_source(tmp_path, (1, 2, 3))
    cold = execute_rule(rule, source, now=NOW - timedelta(days=1))
    assert cold.status == "baseline_insufficient"
    assert execute_rule(rule, source, (cold,), NOW).status == "passed"


def test_extreme_finite_values_do_not_overflow_rule_statistics(tmp_path: Path) -> None:
    """Valid finite business numbers cannot crash an otherwise ordinary row rule."""
    source = business_source(tmp_path, (1e308, 1e308))
    result = execute_rule(rule_of("not_null"), source, now=NOW)
    assert result.passed is True
    assert result.metrics.mean == 1e308


def test_extreme_drift_returns_explicit_error_instead_of_non_json_infinity(tmp_path: Path) -> None:
    """An unrepresentable ratio remains an explicit non-verdict that can be serialized."""
    rule = rule_of("distribution_drift", DqParameters(baseline_runs=1))
    source = business_source(tmp_path, (1e308,))
    cold = execute_rule(rule, source, now=NOW - timedelta(days=1))
    cold = cold.model_copy(update={"metrics": cold.metrics.model_copy(update={"mean": 1e-308})})
    assert execute_rule(rule, source, (cold,), NOW).status == "error"


def test_large_business_table_requires_explicit_bounded_scan_limit(db: Database) -> None:
    """An 18,000-row table fails the default cap and passes only an explicit larger cap."""
    with db.engine.begin() as connection:
        if db.sqlite:
            schema = "main"
            connection.execute(text("CREATE TABLE dq_large_values(value INTEGER)"))
            connection.execute(
                text("INSERT INTO dq_large_values VALUES (:value)"),
                [{"value": value} for value in range(18000)],
            )
        else:
            schema = str(connection.execute(text("SELECT current_schema()")).scalar_one())
            connection.execute(
                text("CREATE TABLE dq_large_values AS SELECT generate_series(1, 18000) AS value")
            )
    source = SourceProperties(
        connection_url=db.engine.url.render_as_string(hide_password=False),
        dialect=db.engine.dialect.name,
    )
    rule = rule_of("not_null").model_copy(
        update={
            "target": DqTarget(
                source_id="demo", schema_name=schema, table="dq_large_values", column="value"
            )
        }
    )
    assert execute_rule(rule, source, now=NOW).status == "error"
    result = execute_rule(rule.model_copy(update={"max_rows": 20000}), source, now=NOW)
    assert result.status == "passed"
    assert result.row_count == 18000


@pytest.mark.parametrize("statistic", ["mean", "stddev", "psi"])
def test_numeric_distribution_rejects_mixed_source_before_baseline_or_comparison(
    tmp_path: Path,
    statistic: Literal["mean", "stddev", "psi"],
) -> None:
    """An illegal text cell cannot disappear from a measured numeric distribution."""
    good_folder, bad_folder = tmp_path / "good", tmp_path / "bad"
    good_folder.mkdir()
    bad_folder.mkdir()
    rule = rule_of("distribution_drift", DqParameters(statistic=statistic, baseline_runs=1))
    cold = execute_rule(rule, business_source(good_folder, (10, 10)), now=NOW - timedelta(days=1))
    mixed = business_source(bad_folder, (10, 10, "invalid"))
    assert execute_rule(rule, mixed, now=NOW).status == "error"
    assert execute_rule(rule, mixed, (cold,), NOW).status == "error"


def test_null_rate_distribution_accepts_non_numeric_non_null_cells(tmp_path: Path) -> None:
    """Null-rate measures missingness across strings, booleans and nonfinite non-NULL values."""
    source = business_source(tmp_path, (10, "text", True, float("inf")))
    rule = rule_of("distribution_drift", DqParameters(statistic="null_rate", baseline_runs=1))
    cold = execute_rule(rule, source, now=NOW - timedelta(days=1))
    assert cold.status == "baseline_insufficient"
    assert execute_rule(rule, source, (cold,), NOW).status == "passed"


@pytest.mark.parametrize("statistic", ["mean", "stddev", "psi"])
@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), float("-inf")])
def test_numeric_distribution_rejects_boolean_and_nonfinite_driver_values(
    monkeypatch: pytest.MonkeyPatch,
    statistic: Literal["mean", "stddev", "psi"],
    invalid: Scalar,
) -> None:
    """Driver-level booleans and nonfinite scalars cannot enter even a cold baseline."""
    rows = QueryResult(columns=["value"], rows=[[10], [invalid]])
    monkeypatch.setattr("datakeel.quality.dq_engine.read_rule_table", lambda *_args: rows)
    rule = rule_of("distribution_drift", DqParameters(statistic=statistic, baseline_runs=1))
    assert execute_rule(rule, SourceProperties(dialect="sqlite"), now=NOW).status == "error"


def test_whole_rule_deadline_rejects_verdict_after_scalar_computation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed scan cannot publish a pass after computation exhausts the deadline."""
    source = business_source(tmp_path, (1, 2))
    ticks = iter((0.0, 0.0, 10.0, 10.0))
    monkeypatch.setattr("datakeel.quality.dq_engine.monotonic", lambda: next(ticks))
    result = execute_rule(rule_of("not_null"), source, now=NOW)
    assert result.status == "error"
    assert "execution timeout" in result.message


def test_adaptive_psi_bins_follow_baseline_scale(tmp_path: Path) -> None:
    """Without explicit edges, baseline deciles fix the bins, so drift shows at any scale."""
    rule = rule_of("distribution_drift", DqParameters(statistic="psi"), 0.25)
    for scale in (0.001, 1, 100000):
        folders = tuple(tmp_path / f"{name}-{scale}" for name in ("baseline", "similar", "shifted"))
        for folder in folders:
            folder.mkdir()
        baseline = tuple(scale * index / 100 for index in range(100))
        similar = tuple(scale * (index + 0.5) / 100 for index in range(100))
        shifted = tuple(value + scale / 2 for value in baseline)
        history = history_for(rule, baseline, folders[0])
        edges = history[0].metrics.bin_edges
        assert len(edges) == 9
        assert all(item.metrics.bin_edges == edges for item in history)
        steady = execute_rule(rule, business_source(folders[1], similar), history, NOW)
        assert (steady.status, steady.actual_value) == ("passed", 0)
        drifted = execute_rule(rule, business_source(folders[2], shifted), history, NOW)
        assert (drifted.status, drifted.metrics.bin_edges) == ("failed", edges)


def test_adaptive_psi_without_numeric_baseline_is_an_error(tmp_path: Path) -> None:
    """An empty baseline cannot invent bins that silently pass a later comparison."""
    rule = rule_of("distribution_drift", DqParameters(statistic="psi", baseline_runs=1))
    empty = execute_rule(rule, business_source(tmp_path, (None,)), now=NOW - timedelta(days=1))
    assert (empty.status, empty.metrics.bin_edges) == ("baseline_insufficient", ())
    other = tmp_path / "numbers"
    other.mkdir()
    assert execute_rule(rule, business_source(other, (1, 2)), (empty,), NOW).status == "error"
