# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Aggregate observed device samples into UTC-aligned fixed-frequency buckets."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import TableData, read_table, write_table
from datakeel.operators.timeseries.common import (
    TimePoint,
    column_index,
    grouped_points,
    numeric_columns,
    points,
    with_summary,
)
from datakeel.operators.timeseries.models import (
    ResampleBucket,
    ResampleParams,
    ResampleSummary,
    SeriesIssue,
)


def _decimal_number(cell: str) -> Decimal | None:
    try:
        number = Decimal(cell)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _aggregate(values: list[Decimal], method: str) -> str:
    if not values:
        return ""
    if method in {"first", "last", "min", "max"}:
        selectors = {
            "first": lambda: values[0],
            "last": lambda: values[-1],
            "min": lambda: min(values),
            "max": lambda: max(values),
        }
        return str(selectors[method]())
    # A local decimal context preserves large counters and decimal sensor resolution.
    places = min(int(value.as_tuple().exponent) for value in values)
    digits = max(value.adjusted() for value in values) - places + 1
    with localcontext() as context:
        context.prec = max(28, digits + len(str(len(values))) + 2)
        total = sum(values, start=Decimal(0))
        return str(total / len(values) if method == "mean" else total)


def _bucket_row(
    data: TableData, group: list[TimePoint], columns: list[str], params: ResampleParams
) -> tuple[str, ...]:
    first = group[0]
    row: list[str] = []
    for index, name in enumerate(data.columns):
        cells = [data.rows[item.index][index] for item in group]
        if name == params.time_column:
            row.append(str((first.milliseconds // params.interval_ms) * params.interval_ms))
        elif name in columns:
            values = [_decimal_number(cell) for cell in cells]
            row.append(
                _aggregate([value for value in values if value is not None], params.aggregation)
            )
        else:
            row.append(cells[0] if len(set(cells)) == 1 else "")
    return tuple(row)


def _resample(data: TableData, params: ResampleParams) -> tuple[TableData, ResampleSummary]:
    items, invalid = points(data, params)
    columns = numeric_columns(data, params, params.value_columns)
    column_index(data, params.time_column)
    rows: list[tuple[str, ...]] = []
    sources: list[int] = []
    provenance: list[ResampleBucket] = []
    for group in grouped_points(items).values():
        buckets: dict[int, list[TimePoint]] = defaultdict(list)
        for item in group:
            buckets[item.milliseconds // params.interval_ms].append(item)
        for bucket in buckets.values():
            rows.append(_bucket_row(data, bucket, columns, params))
            sources.append(bucket[0].row)
            start = (bucket[0].milliseconds // params.interval_ms) * params.interval_ms
            provenance.append(
                ResampleBucket(
                    device=bucket[0].device,
                    start_ms=start,
                    end_ms=start + params.interval_ms,
                    rows=tuple(point.row for point in bucket),
                )
            )
    summary = ResampleSummary(
        row_count=len(rows),
        issues=tuple(invalid),
        interval_ms=params.interval_ms,
        aggregation=params.aggregation,
        input_rows=len(data.rows),
        output_rows=len(rows),
        value_columns=tuple(columns),
        buckets=tuple(provenance),
    )
    return data.model_copy(update={"rows": tuple(rows), "row_numbers": tuple(sources)}), summary


def execute(files: list[FileItem], output_dir: Path, params: ResampleParams) -> OperatorResult:
    """Aggregate populated buckets without inventing samples across missing intervals."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    for file in files:
        data, summary = _resample(read_table(file), params)
        output.append(with_summary(write_table(file, output_dir, data), "resample", summary))
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator("timeseries.resample", "table", "transform", ResampleParams, execute)
