# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sort per-device timestamps and deterministically remove duplicate keys."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import TableData, read_table, write_table
from datakeel.operators.timeseries.common import TimePoint, grouped_points, points, with_summary
from datakeel.operators.timeseries.models import OrderParams, OrderSummary, SeriesIssue


def _ordering_issue(rule: str, before: TimePoint, after: TimePoint, column: str) -> SeriesIssue:
    return SeriesIssue(
        rule=rule,
        column=column,
        device=after.device,
        rows=(before.row, after.row),
        start_ms=min(before.milliseconds, after.milliseconds),
        end_ms=max(before.milliseconds, after.milliseconds),
        threshold=0,
        window=2,
        detail="Repeated device/timestamp key"
        if rule == "duplicate_timestamp"
        else "Timestamp decreases",
        recommendation="Sort within each device and keep the configured duplicate row",
    )


def _order_issues(items: list[TimePoint], params: OrderParams) -> list[SeriesIssue]:
    previous: dict[str, TimePoint] = {}
    seen: dict[tuple[str, int], TimePoint] = {}
    issues: list[SeriesIssue] = []
    for item in items:
        before = previous.get(item.device)
        duplicate = seen.get((item.device, item.milliseconds))
        if before is not None and item.milliseconds < before.milliseconds:
            issues.append(_ordering_issue("out_of_order", before, item, params.time_column))
        if duplicate is not None:
            issues.append(
                _ordering_issue("duplicate_timestamp", duplicate, item, params.time_column)
            )
        previous[item.device] = item
        seen.setdefault((item.device, item.milliseconds), item)
    return issues


def _ordered(data: TableData, params: OrderParams) -> tuple[TableData, OrderSummary]:
    items, invalid = points(data, params)
    issues = _order_issues(items, params)
    kept: list[TimePoint] = []
    for group in grouped_points(items).values():
        keys: dict[int, TimePoint] = {}
        for item in group:
            if params.keep == "last" or item.milliseconds not in keys:
                keys[item.milliseconds] = item
        kept.extend(keys.values())
    # Invalid timestamps remain visible at the end rather than being silently discarded.
    indices = [item.index for item in kept]
    valid_indices = {item.index for item in items}
    indices.extend(index for index in range(len(data.rows)) if index not in valid_indices)
    summary = OrderSummary(
        row_count=len(data.rows),
        issues=(*invalid, *issues),
        out_of_order_count=sum(issue.rule == "out_of_order" for issue in issues),
        duplicate_count=len(items) - len(kept),
        retained_count=len(indices),
        keep=params.keep,
    )
    return data.model_copy(
        update={
            "rows": tuple(data.rows[index] for index in indices),
            "row_numbers": tuple(data.row_numbers[index] for index in indices),
        }
    ), summary


def execute(files: list[FileItem], output_dir: Path, params: OrderParams) -> OperatorResult:
    """Preserve original source row coordinates through sorting and deduplication."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    for file in files:
        data, summary = _ordered(read_table(file), params)
        output.append(with_summary(write_table(file, output_dir, data), "order_dedup", summary))
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator("timeseries.order_dedup", "table", "clean", OrderParams, execute)
