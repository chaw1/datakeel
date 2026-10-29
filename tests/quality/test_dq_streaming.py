# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete scans cross batch boundaries without retaining rows or reference tables."""

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqParameters
from datakeel.quality.dq_engine import execute_rule
from tests.quality.test_dq_engine import NOW, business_source, rule_of


def test_constraints_cover_rows_and_reference_values_beyond_batch_size(tmp_path: Path) -> None:
    """Duplicate and orphan counts include late rows and references beyond a batch."""
    source = business_source(tmp_path, (1, 2, 3, 4, 4, 9, None), (1, 2, 3, 4))
    cases = (
        ("not_null", DqParameters(), 1),
        ("unique", DqParameters(), 2),
        ("range", DqParameters(minimum=2, maximum=4), 2),
        ("accepted_values", DqParameters(values=(1, 2, 3, 4)), 1),
        (
            "referential_integrity",
            DqParameters(reference_table="codes", reference_column="code"),
            1,
        ),
    )
    for kind, parameters, expected in cases:
        rule = rule_of(kind, parameters).model_copy(update={"max_rows": 2})
        result = execute_rule(rule, source, now=NOW)
        assert (result.status, result.failed_count) == ("failed", expected)
        assert (result.rows_total, result.rows_scanned, result.coverage) == (7, 7, "complete")
        assert result.actual_value == expected / 7


def test_regex_stream_counts_failures_after_multiple_batches(tmp_path: Path) -> None:
    """Only the first five redacted samples are retained while every row contributes."""
    source = business_source(tmp_path, ("OK",) * 9 + ("bad",) * 7 + (None,))
    rule = rule_of("regex", DqParameters(pattern="[A-Z]+"))
    result = execute_rule(rule.model_copy(update={"max_rows": 2}), source, now=NOW)
    assert (result.status, result.failed_count, result.rows_scanned) == ("failed", 7, 17)
    assert tuple(sample.row_number for sample in result.samples) == (10, 11, 12, 13, 14)
    assert result.coverage == "complete"


def test_assertion_limits_only_returned_violations_and_reports_source_coverage(
    tmp_path: Path,
) -> None:
    """An oversized source is valid; an oversized assertion result is an explicit error."""
    source = business_source(tmp_path, tuple(range(21)))
    rule = rule_of(
        "sql_assertion", DqParameters(sql="SELECT value FROM observations WHERE value > 19")
    )
    result = execute_rule(rule.model_copy(update={"max_rows": 2}), source, now=NOW)
    assert (result.status, result.failed_count) == ("failed", 1)
    assert (result.rows_total, result.rows_scanned, result.coverage) == (21, 21, "complete")
    too_many = rule.model_copy(
        update={"params": DqParameters(sql="SELECT value FROM observations"), "max_rows": 2}
    )
    result = execute_rule(too_many, source, now=NOW)
    assert result.status == "error"
    assert "result row limit" in result.message
    assert (result.passed, result.rows_total, result.rows_scanned, result.coverage) == (
        None,
        None,
        0,
        "unknown",
    )


def test_distribution_stream_preserves_exact_deciles_and_population_moments(tmp_path: Path) -> None:
    """First-observation deciles and later histograms do not depend on batch size."""
    source = business_source(tmp_path, (*range(21), None))
    rule = rule_of("distribution_drift", DqParameters(statistic="psi", baseline_runs=1))
    rule = rule.model_copy(update={"max_rows": 2})
    cold = execute_rule(rule, source, now=NOW - timedelta(days=1))
    assert cold.status == "baseline_insufficient"
    assert cold.metrics.bin_edges == (2, 4, 6, 8, 10, 12, 14, 16, 18)
    assert cold.metrics.mean == pytest.approx(10)
    assert cold.metrics.stddev == pytest.approx((110 / 3) ** 0.5)
    result = execute_rule(rule, source, (cold,), NOW)
    assert result.status == "passed"
    assert result.actual_value == 0
    assert (result.rows_total, result.rows_scanned, result.coverage) == (22, 22, "complete")


def test_timed_out_stream_has_no_partial_verdict(tmp_path: Path) -> None:
    """Even previously seen good batches cannot yield a passing timeout result."""
    source = business_source(tmp_path, ("OK",) * 10000)
    rule = rule_of("regex", DqParameters(pattern="[A-Z]+"))
    result = execute_rule(rule.model_copy(update={"timeout_ms": 1, "max_rows": 2}), source, now=NOW)
    assert result.status == "error"
    assert (result.passed, result.rows_total, result.rows_scanned, result.coverage) == (
        None,
        None,
        0,
        "unknown",
    )


def test_aggregate_moments_preserve_variance_and_minimum_integer(tmp_path: Path) -> None:
    """Database-side scaling avoids integer overflow and retains population variance."""
    source = business_source(tmp_path, (1, 2, 3))
    result = execute_rule(rule_of("range", DqParameters(minimum=0)), source, now=NOW)
    assert result.metrics.mean == pytest.approx(2)
    assert result.metrics.stddev == pytest.approx((2 / 3) ** 0.5)
    other = tmp_path / "extreme"
    other.mkdir()
    source = business_source(other, (-9223372036854775808, 0, float("inf")))
    result = execute_rule(rule_of("range", DqParameters(minimum=-1e20)), source, now=NOW)
    assert (result.status, result.failed_count) == ("failed", 1)
    assert result.metrics.mean == pytest.approx(-4611686018427387904)


def test_sqlite_scalar_equality_keeps_types_and_case_with_column_affinity(tmp_path: Path) -> None:
    """Pushdown keeps text distinct from numbers and does not inherit NOCASE collation."""
    path = tmp_path / "typed.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE observations(value TEXT COLLATE NOCASE)")
        connection.execute("CREATE TABLE codes(code INTEGER)")
        connection.executemany(
            "INSERT INTO observations VALUES (?)", [("1",), ("2",), ("A",), ("a",)]
        )
        connection.execute("INSERT INTO codes VALUES (1)")
    source = SourceProperties(connection_url=f"sqlite:///{path}", dialect="sqlite")
    assert execute_rule(rule_of("unique"), source, now=NOW).failed_count == 0
    numeric = rule_of("accepted_values", DqParameters(values=(1,)))
    assert execute_rule(numeric, source, now=NOW).failed_count == 4
    text = rule_of("accepted_values", DqParameters(values=("a",)))
    assert execute_rule(text, source, now=NOW).failed_count == 3
    reference = rule_of(
        "referential_integrity", DqParameters(reference_table="codes", reference_column="code")
    )
    assert execute_rule(reference, source, now=NOW).failed_count == 4


def test_adaptive_psi_ties_cross_batch_boundaries_without_changing_bins(tmp_path: Path) -> None:
    """A boundary value's whole equal-value group goes into the upper histogram bucket."""
    source = business_source(tmp_path, (None, 0, 0, 0, 1, 1, 2, 2, 2, 2, 2))
    rule = rule_of("distribution_drift", DqParameters(statistic="psi", baseline_runs=1))
    result = execute_rule(rule.model_copy(update={"max_rows": 2}), source, now=NOW)
    assert result.status == "baseline_insufficient"
    assert result.metrics.bin_edges == (0, 1, 2)
    assert result.metrics.histogram == (0, 0.3, 0.2, 0.5)
