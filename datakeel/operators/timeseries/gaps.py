# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect missing-sample intervals independently within each device."""

from itertools import pairwise
from pathlib import Path
from statistics import median

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.table.io import read_table
from datakeel.operators.timeseries.common import TimePoint, grouped_points, points, with_summary
from datakeel.operators.timeseries.models import GapInterval, GapsParams, GapsSummary, SeriesIssue


def _intervals(group: list[TimePoint], params: GapsParams) -> list[GapInterval]:
    deltas = [after.milliseconds - before.milliseconds for before, after in pairwise(group)]
    positives = [delta for delta in deltas if delta > 0]
    if not positives:
        return []
    expected = params.expected_interval_ms or max(1, int(median(positives)))
    result: list[GapInterval] = []
    for before, after in pairwise(group):
        delta = after.milliseconds - before.milliseconds
        if delta > expected * params.tolerance:
            result.append(
                GapInterval(
                    device=before.device,
                    start_ms=before.milliseconds,
                    end_ms=after.milliseconds,
                    gap_ms=delta - expected,
                    expected_interval_ms=expected,
                    missing_samples=max(1, round(delta / expected) - 1),
                    rows=(before.row, after.row),
                )
            )
    return result


def _gap_issue(interval: GapInterval, params: GapsParams) -> SeriesIssue:
    return SeriesIssue(
        rule="sampling_gap",
        column=params.time_column,
        device=interval.device,
        rows=interval.rows,
        start_ms=interval.start_ms,
        end_ms=interval.end_ms,
        threshold=interval.expected_interval_ms * params.tolerance,
        window=2,
        observed=float(interval.end_ms - interval.start_ms),
        detail=f"{interval.missing_samples} expected samples missing; gap_ms={interval.gap_ms}",
        recommendation="Recover missing samples or explicitly mark the missing interval",
    )


def execute(files: list[FileItem], _output_dir: Path, params: GapsParams) -> OperatorResult:
    """Annotate gap intervals without interpolating or altering observations."""
    output: list[FileItem] = []
    issues: list[SeriesIssue] = []
    for file in files:
        data = read_table(file)
        items, invalid = points(data, params)
        intervals = [
            interval
            for group in grouped_points(items).values()
            for interval in _intervals(group, params)
        ]
        summary = GapsSummary(
            row_count=len(data.rows),
            issues=(*invalid, *(_gap_issue(interval, params) for interval in intervals)),
            intervals=tuple(intervals),
            total_gap_ms=sum(interval.gap_ms for interval in intervals),
        )
        output.append(with_summary(file, "gaps", summary))
        issues.extend(summary.issues)
    return summarize(files, output, [issue.model_dump(mode="json") for issue in issues])


OPERATOR = Operator("timeseries.gaps", "table", "quality", GapsParams, execute)
