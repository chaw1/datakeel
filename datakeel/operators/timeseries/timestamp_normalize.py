# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize ISO and epoch timestamps to UTC milliseconds with source evidence."""

from collections import Counter, defaultdict
from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import TableData, read_table, write_table
from datakeel.operators.timeseries.common import column_index, invalid_time, with_summary
from datakeel.operators.timeseries.models import SeriesIssue, TimestampParams, TimestampSummary
from datakeel.operators.timeseries.parsing import ParsedTime, parse_time


def _mixed_issues(
    observations: dict[str, list[tuple[int, ParsedTime]]], column: str
) -> list[SeriesIssue]:
    issues: list[SeriesIssue] = []
    for device, items in sorted(observations.items()):
        zones = {item.timezone.replace("+0000", "UTC") for _, item in items}
        if len(zones) <= 1:
            continue
        dominant = Counter(item.timezone.replace("+0000", "UTC") for _, item in items).most_common(
            1
        )[0][0]
        differing = [
            (row, item) for row, item in items if item.timezone.replace("+0000", "UTC") != dominant
        ]
        times = [item.milliseconds for _, item in differing]
        issues.append(
            SeriesIssue(
                rule="timezone_mixed",
                column=column,
                device=device,
                rows=tuple(row for row, _ in differing),
                start_ms=min(times),
                end_ms=max(times),
                threshold=1,
                window=len(items),
                observed=float(len(zones)),
                detail=(
                    f"Multiple timezone representations; evidence differs from dominant {dominant}"
                ),
                recommendation="Declare the source timezone and standardize timestamps to UTC",
            )
        )
    return issues


def _normalize(data: TableData, params: TimestampParams) -> tuple[TableData, TimestampSummary]:
    time_index = column_index(data, params.time_column)
    device_index = (
        None if params.device_column is None else column_index(data, params.device_column)
    )
    observations: dict[str, list[tuple[int, ParsedTime]]] = defaultdict(list)
    rows: list[tuple[str, ...]] = []
    issues: list[SeriesIssue] = []
    for index, row in enumerate(data.rows):
        values = list(row)
        device = "" if device_index is None else row[device_index]
        try:
            parsed = parse_time(row[time_index], params.naive_timezone, params.numeric_unit)
            values[time_index] = str(parsed.milliseconds)
            observations[device].append((data.row_numbers[index], parsed))
        except ValidationError:
            values[time_index] = ""
            issues.append(invalid_time(params.time_column, device, data.row_numbers[index]))
        rows.append(tuple(values))
    valid = [item for group in observations.values() for _, item in group]
    invalid_count = len(issues)
    issues.extend(_mixed_issues(observations, params.time_column))
    summary = TimestampSummary(
        row_count=len(rows),
        issues=tuple(issues),
        formats=tuple(sorted({item.format for item in valid})),
        timezones=tuple(sorted({item.timezone for item in valid})),
        inference_basis=(
            f"Naive ISO timestamps use declared timezone {params.naive_timezone}; "
            f"numeric_unit={params.numeric_unit}; auto uses absolute epoch magnitude "
            "100000000000 to distinguish milliseconds from seconds; DST folds/gaps rejected"
        ),
        invalid_count=invalid_count,
    )
    return data.model_copy(update={"rows": tuple(rows)}), summary


def execute(files: list[FileItem], output_dir: Path, params: TimestampParams) -> OperatorResult:
    """Materialize normalized UTC milliseconds and preserve all source columns."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    # Validate configuration even when the table contains only explicit offsets.
    parse_time("2000-01-01T00:00:00", params.naive_timezone)
    for file in files:
        data, summary = _normalize(read_table(file), params)
        output.append(
            with_summary(write_table(file, output_dir, data), "timestamp_normalize", summary)
        )
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator(
    "timeseries.timestamp_normalize", "table", "normalize", TimestampParams, execute
)
