# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Comparison values use actual query baselines and calendar-aligned dimensions."""

from datetime import UTC, date, datetime

import pytest

from datakeel.ask.comparisons import comparison_changes, comparison_message
from datakeel.ask.followup import previous_period
from datakeel.ask.service import ask_data
from datakeel.core.ask_frame_models import AskComparison, AskQueryFrame
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import (
    CompileRequest,
    MetricCard,
    QueryResult,
    SemanticLayer,
    TimeRange,
)
from datakeel.metrics.compiler import compile_metric
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_year_and_month_comparisons_match_two_independent_queries(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """The public comparison exposes evidence from the previous metric execution."""
    answer = ask_data(
        db, AskRequest(question="2026年9月华南零售额环比", reference_instant=REFERENCE)
    )
    prior = ask_data(db, AskRequest(question="2026年8月华南零售额", reference_instant=REFERENCE))
    assert answer.status == "answered"
    assert answer.comparison
    assert answer.result
    assert answer.comparison.previous_result == prior.result
    assert answer.comparison.previous_time_range == TimeRange(
        start=date(2026, 8, 1), end=date(2026, 9, 1)
    )
    change = answer.comparison.changes[0]
    assert change.current_value is not None
    assert change.previous_value is not None
    assert change.delta is not None
    assert change.delta == pytest.approx(change.current_value - change.previous_value)
    assert change.percent_change == pytest.approx(change.delta / abs(change.previous_value) * 100)


def test_time_buckets_align_by_calendar_period_not_absolute_date() -> None:
    """A January baseline compares with this January, without shifting other groups."""
    current = QueryResult(
        columns=["region", "time_bucket", "value"], rows=[["E", "2026-01-01", 30]]
    )
    previous = QueryResult(columns=current.columns, rows=[["E", "2025-01-01", 20]])
    frame = AskQueryFrame(
        metric_id="revenue",
        time_range=TimeRange(start=date(2026, 1, 1), end=date(2026, 4, 1)),
        time_grain="month",
        comparison="year_over_year",
    )
    interval = TimeRange(start=date(2025, 1, 1), end=date(2025, 4, 1))
    change = comparison_changes(current, previous, frame, interval)[0]
    assert (change.delta, change.percent_change) == (10, 50)


def test_missing_or_zero_baseline_never_invents_a_percentage() -> None:
    """Null, absent and zero comparison values remain explicitly uncomputable."""
    columns = ["region", "value"]
    current = QueryResult(columns=columns, rows=[["E", 10], ["S", 20], ["N", None]])
    previous = QueryResult(columns=columns, rows=[["E", 0], ["N", 8]])
    changes = comparison_changes(
        current,
        previous,
        AskQueryFrame(metric_id="revenue"),
        TimeRange(start=date(2025, 1, 1), end=date(2026, 1, 1)),
    )
    assert changes[0].delta == 10
    assert changes[0].percent_change is None
    assert changes[1].previous_value is None
    assert changes[1].delta is None
    assert changes[2].current_value is None
    assert changes[2].delta is None


def test_previous_period_handles_leap_days_and_unaligned_periods() -> None:
    """Calendar comparison clamps leap days; arbitrary date ranges use equal duration."""
    leap = AskQueryFrame(
        metric_id="x", time_range=TimeRange(start=date(2024, 2, 29), end=date(2024, 3, 1))
    )
    assert previous_period(leap, "year_over_year") == TimeRange(
        start=date(2023, 2, 28), end=date(2023, 3, 1)
    )
    days = AskQueryFrame(
        metric_id="x", time_range=TimeRange(start=date(2026, 8, 10), end=date(2026, 8, 15))
    )
    assert previous_period(days, "period_over_period") == TimeRange(
        start=date(2026, 8, 5), end=date(2026, 8, 10)
    )
    assert previous_period(AskQueryFrame(metric_id="x"), "year_over_year") is None


def test_as_of_comparison_requires_an_explicit_bounded_interval(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Cumulative dates cannot overflow calendar shifting or produce a guessed baseline."""
    answer = ask_data(
        db, AskRequest(question="截至2026年9月零售额同比", reference_instant=REFERENCE)
    )
    assert answer.status == "clarification"
    assert answer.result is None
    assert answer.comparison is None


def test_previous_week_daily_buckets_align_across_month_boundary() -> None:
    """A seven-day comparison shifts by seven days even when its dates cross a month."""
    current = QueryResult(columns=["time_bucket", "value"], rows=[["2026-10-01", 5]])
    previous = QueryResult(columns=current.columns, rows=[["2026-09-24", 4]])
    frame = AskQueryFrame(
        metric_id="x",
        time_range=TimeRange(start=date(2026, 10, 1), end=date(2026, 10, 8)),
        time_grain="day",
        comparison="period_over_period",
    )
    changes = comparison_changes(
        current, previous, frame, TimeRange(start=date(2026, 9, 24), end=date(2026, 10, 1))
    )
    assert changes[0].previous_value == 4
    assert changes[0].delta == 1
    assert changes[0].percent_change == 25


def test_zero_baseline_message_explains_why_the_percentage_is_unavailable(
    layer: SemanticLayer,
) -> None:
    """A measured zero baseline is distinguished from missing data and never divides by zero."""
    metric = layer.metrics[0]
    frame = AskQueryFrame(metric_id=metric.id)
    interval = TimeRange(start=date(2025, 1, 1), end=date(2026, 1, 1))
    previous = QueryResult(columns=["value"], rows=[[0]])
    changes = comparison_changes(
        QueryResult(columns=["value"], rows=[[5]]), previous, frame, interval
    )
    comparison = AskComparison(
        mode="year_over_year",
        previous_time_range=interval,
        previous_sql=compile_metric(
            MetricCard(definition=metric), layer.dimensions, CompileRequest()
        ),
        previous_result=previous,
        changes=changes,
    )
    assert changes[0].percent_change is None
    assert "上一期值为0" in comparison_message(comparison)
    assert "百分比" in comparison_message(comparison)


def test_calendar_underflow_is_unavailable_instead_of_raising_or_guessing_dates() -> None:
    """The earliest valid calendar interval has no representable preceding year or period."""
    earliest = AskQueryFrame(
        metric_id="x", time_range=TimeRange(start=date(1, 1, 1), end=date(1, 1, 2))
    )
    assert previous_period(earliest, "year_over_year") is None
    assert previous_period(earliest, "period_over_period") is None
