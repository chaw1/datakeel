# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect stuck readings, jumps, bounds violations and robust statistical outliers."""

from itertools import pairwise
from pathlib import Path
from statistics import median

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import TableData, read_table
from datakeel.operators.timeseries.common import (
    TimePoint,
    column_index,
    grouped_points,
    numeric_columns,
    points,
    with_summary,
)
from datakeel.operators.timeseries.models import AnomalyParams, AnomalySummary, SeriesIssue
from datakeel.operators.timeseries.parsing import finite_number
from datakeel.operators.timeseries.rules import (
    SignalPoint,
    jump_issues,
    range_issues,
    robust_issues,
    stuck_issues,
)


def _signals(data: TableData, group: list[TimePoint], column: str) -> list[list[SignalPoint]]:
    index = column_index(data, column)
    deltas = [
        after.milliseconds - before.milliseconds
        for before, after in pairwise(group)
        if after.milliseconds > before.milliseconds
    ]
    cadence = median(deltas) if deltas else None
    segments: list[list[SignalPoint]] = []
    current: list[SignalPoint] = []
    for point in group:
        value = finite_number(data.rows[point.index][index])
        discontinuous = (
            current
            and cadence is not None
            and (point.milliseconds - current[-1].milliseconds > cadence * 1.5)
        )
        if (value is None or discontinuous) and current:
            segments.append(current)
            current = []
        if value is not None:
            current.append(SignalPoint(**point.model_dump(), value=value))
    if current:
        segments.append(current)
    return segments


def _inspect(
    data: TableData, items: list[TimePoint], columns: list[str], params: AnomalyParams
) -> list[SeriesIssue]:
    issues: list[SeriesIssue] = []
    bounds = {item.column: item for item in params.ranges}
    for column in columns:
        for group in grouped_points(items).values():
            for signal in _signals(data, group, column):
                stuck = stuck_issues(signal, column, params.stuck_min_points)
                issues.extend(stuck)
                excluded = frozenset(row for issue in stuck for row in issue.rows)
                issues.extend(robust_issues(signal, column, params, excluded))
                if params.jump_threshold is not None:
                    issues.extend(jump_issues(signal, column, params.jump_threshold))
                if column in bounds:
                    issues.extend(range_issues(signal, column, bounds[column]))
    return issues


def _interval_count(issues: list[SeriesIssue]) -> int:
    intervals = sorted(
        (issue.device, issue.column, issue.start_ms, issue.end_ms)
        for issue in issues
        if issue.start_ms is not None and issue.end_ms is not None
    )
    ends: dict[tuple[str, str], int] = {}
    count = 0
    for device, column, start, end in intervals:
        key = (device, column)
        previous_end = ends.get(key)
        if previous_end is None or start > previous_end:
            count += 1
        ends[key] = max(end, previous_end) if previous_end is not None else end
    return count


def execute(files: list[FileItem], _output_dir: Path, params: AnomalyParams) -> OperatorResult:
    """Inspect each device independently and annotate source rows without repairing values."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    for file in files:
        data = read_table(file)
        items, invalid = points(data, params)
        columns = numeric_columns(data, params, params.value_columns)
        for bounds in params.ranges:
            column_index(data, bounds.column)
            if bounds.column not in columns:
                columns.append(bounds.column)
        detected = _inspect(data, items, columns, params)
        summary = AnomalySummary(
            row_count=len(data.rows),
            issues=(*invalid, *detected),
            anomaly_intervals=_interval_count(detected),
            value_columns=tuple(columns),
        )
        output.append(with_summary(file, "anomaly", summary))
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator("timeseries.anomaly", "table", "quality", AnomalyParams, execute)
