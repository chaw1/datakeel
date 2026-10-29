# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute comparisons only from actual current and baseline metric engine results."""

import re
from datetime import date

from datakeel.ask.followup_cues import comparison_hits
from datakeel.ask.time_atoms import shift_months
from datakeel.core.ask_frame_models import AskComparison, AskQueryFrame, ComparisonChange
from datakeel.core.metric_models import QueryResult, Scalar, TimeRange

_QUARTER_MONTHS = 3
_EXPLICIT_PERIODS = (
    (
        1,
        re.compile(
            r"上个?月|(?:previous|prior)\s+month|month[ -]over[ -]month|\bmom\b", re.IGNORECASE
        ),
    ),
    (
        3,
        re.compile(
            r"上个?季度|(?:previous|prior)\s+quarter|quarter[ -]over[ -]quarter|\bqoq\b",
            re.IGNORECASE,
        ),
    ),
)


def comparison_unit_mismatch(question: str, frame: AskQueryFrame) -> bool:
    """Reject explicit month/quarter baselines unless the current calendar grain matches."""
    units = {
        months
        for mode, hit in comparison_hits(question)
        if mode == "period_over_period"
        for months, pattern in _EXPLICIT_PERIODS
        if pattern.search(hit.group())
    }
    interval = frame.time_range
    if not units or interval is None or frame.comparison != "period_over_period":
        return False
    months = (interval.end.year - interval.start.year) * 12
    months += interval.end.month - interval.start.month
    aligned = interval.start.day == interval.end.day == 1
    return not aligned or any(
        months != unit or (unit == _QUARTER_MONTHS and interval.start.month not in {1, 4, 7, 10})
        for unit in units
    )


def comparison_changes(
    current: QueryResult, previous: QueryResult, frame: AskQueryFrame, interval: TimeRange
) -> tuple[ComparisonChange, ...]:
    """Align dimension keys and calendar buckets; never turn absent data into zero."""
    value_index = current.columns.index("value")
    earlier = {
        _key(row, previous.columns, frame, interval): row[value_index] for row in previous.rows
    }
    changes: list[ComparisonChange] = []
    for row in current.rows:
        key = tuple(value for index, value in enumerate(row) if index != value_index)
        now, before = _number(row[value_index]), _number(earlier.get(key))
        delta = None if now is None or before is None else now - before
        changes.append(
            ComparisonChange(
                dimensions=key,
                current_value=now,
                previous_value=before,
                delta=delta,
                percent_change=None if delta is None or not before else delta / abs(before) * 100,
            )
        )
    return tuple(changes)


def _number(value: Scalar) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _key(
    row: list[Scalar], columns: list[str], frame: AskQueryFrame, interval: TimeRange
) -> tuple[Scalar, ...]:
    values: list[Scalar] = []
    for column, original in zip(columns, row, strict=True):
        value = original
        if column == "value":
            continue
        if column == "time_bucket" and isinstance(value, str) and frame.time_range:
            current = frame.time_range
            months = (current.start.year - interval.start.year) * 12
            months += current.start.month - interval.start.month
            day = date.fromisoformat(value)
            calendar_aligned = (
                current.start.day == current.end.day == interval.start.day == interval.end.day == 1
            )
            value = (
                shift_months(day, months)
                if frame.comparison == "year_over_year" or calendar_aligned
                else day + (current.start - interval.start)
            ).isoformat()
        values.append(value)
    return tuple(values)


def comparison_message(comparison: AskComparison | None) -> str:
    """Explain unavailable baselines rather than asserting an invented percentage."""
    if comparison is not None and any(item.previous_value is None for item in comparison.changes):
        return "答案来自登记指标与只读查询。上一期没有对应数据,无法计算部分变化。"
    if comparison is not None and any(item.previous_value == 0 for item in comparison.changes):
        return "答案来自登记指标与只读查询。上一期值为0,无法计算对应变化百分比。"
    return "答案来自登记指标与只读查询。"
