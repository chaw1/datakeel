# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve source coordinates and typed evidence across time-series operators."""

from collections import defaultdict
from typing import TYPE_CHECKING, cast

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem, Record
from datakeel.operators.base import annotate
from datakeel.operators.timeseries.models import SeriesIssue, SeriesSummary, TimeParams
from datakeel.operators.timeseries.parsing import finite_number, parse_time

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.operators.table.io import TableData


MIN_CONTINUOUS_VALUES = 3


class TimePoint(Record):
    """Link a valid UTC timestamp to its original source coordinate."""

    index: int
    row: int
    milliseconds: int
    device: str


def column_index(data: "TableData", column: str) -> int:
    """Resolve a declared column or reject it before processing."""
    try:
        return data.columns.index(column)
    except ValueError as exc:
        msg = f"Unknown table column: {column}"
        raise ValidationError(msg) from exc


def points(data: "TableData", params: TimeParams) -> tuple[list[TimePoint], list[SeriesIssue]]:
    """Read valid timestamps and retain invalid source cells as typed issues."""
    time_index = column_index(data, params.time_column)
    device_index = (
        None if params.device_column is None else column_index(data, params.device_column)
    )
    result: list[TimePoint] = []
    issues: list[SeriesIssue] = []
    for index, row in enumerate(data.rows):
        device = "" if device_index is None else row[device_index]
        try:
            milliseconds = parse_time(row[time_index], numeric_unit="ms").milliseconds
        except ValidationError:
            issues.append(invalid_time(params.time_column, device, data.row_numbers[index]))
            continue
        result.append(
            TimePoint(
                index=index, row=data.row_numbers[index], milliseconds=milliseconds, device=device
            )
        )
    return result, issues


def invalid_time(column: str, device: str, row: int) -> SeriesIssue:
    """Describe an invalid or ambiguous timestamp without copying source values."""
    return SeriesIssue(
        rule="invalid_timestamp",
        column=column,
        device=device,
        rows=(row,),
        detail="Timestamp is invalid, missing, or has an ambiguous local timezone",
        recommendation="Correct the timestamp and supply an explicit UTC offset",
    )


def grouped_points(items: list[TimePoint]) -> dict[str, list[TimePoint]]:
    """Partition by device and return deterministic timestamp/source ordering."""
    groups: dict[str, list[TimePoint]] = defaultdict(list)
    for item in items:
        groups[item.device].append(item)
    return {
        device: sorted(group, key=lambda point: (point.milliseconds, point.index))
        for device, group in sorted(groups.items())
    }


def numeric_columns(data: "TableData", params: TimeParams, requested: list[str]) -> list[str]:
    """Resolve explicit signals or infer noncategorical, nonidentifier numeric columns."""
    if requested:
        for name in requested:
            column_index(data, name)
        return list(dict.fromkeys(requested))
    result: list[str] = []
    for index, column in enumerate(data.columns):
        lower = column.lower()
        excluded = column in {params.time_column, params.device_column} or any(
            token in lower for token in ("_id", "phone", "switch", "event", "level", "state")
        )
        values = [finite_number(row[index]) for row in data.rows if row[index].strip()]
        finite = [value for value in values if value is not None]
        if (
            not excluded
            and finite
            and len(finite) == len(values)
            and (
                len(set(finite)) > MIN_CONTINUOUS_VALUES
                or any(
                    token in lower
                    for token in ("temperature", "pressure", "speed", "flow", "voltage")
                )
            )
        ):
            result.append(column)
    return result


def with_summary(file: FileItem, name: str, summary: SeriesSummary) -> FileItem:
    """Append one typed measurement while preserving earlier chain summaries."""
    previous = file.metadata.get("timeseries", {})
    values: dict[str, JsonValue] = (
        cast("dict[str, JsonValue]", previous).copy() if isinstance(previous, dict) else {}
    )
    values[name] = summary.model_dump(mode="json")
    return annotate(file, timeseries=cast("JsonValue", values))
