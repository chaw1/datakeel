# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Render a reproducible table-profile chapter from typed, persisted measurements."""

from datakeel.quality.models import ChapterView
from datakeel.quality.tabular_models import TabularAssessment, TabularFileAssessment, TabularFinding

ROW_PREVIEW_LIMIT = 12


def _location(finding: TabularFinding) -> str:
    rows = ", ".join(str(row) for row in finding.rows[:ROW_PREVIEW_LIMIT])
    if len(finding.rows) > ROW_PREVIEW_LIMIT:
        rows += f", … ({len(finding.rows)} source rows)"
    return (
        f"device={finding.device or 'all'}; rows=[{rows}]; "
        f"UTC ms={finding.start_ms}..{finding.end_ms}; "
        f"threshold={finding.threshold}; window={finding.window}"
    )


def _file_lines(file: TabularFileAssessment) -> list[str]:
    lines = [
        f"### {file.filename}",
        (
            f"Rows: {file.row_count}; anomaly intervals: {file.anomaly_intervals}; "
            f"total missing-sample duration: {file.total_gap_ms} ms "
            f"({file.total_gap_ms / 1000:g} s)."
        ),
    ]
    for column in file.columns:
        rules = sorted({item.rule for item in file.findings if item.column == column.name})
        lines.append(
            f"- {column.name}: type={column.inferred_type}; null={column.null_rate:.2%}; "
            f"unique={column.unique_rate:.2%}; problems={', '.join(rules) or 'none detected'}."
        )
    lines.extend(
        f"- [{finding.rule}] {finding.column}; {_location(finding)}. "
        f"{finding.detail}. Repair: {finding.recommendation}."
        for finding in file.findings
    )
    return lines


def tabular_chapter(assessment: TabularAssessment) -> ChapterView:
    """Describe each column, anomaly interval, missing duration and suggested repair."""
    return ChapterView(
        title="表格与时序剖析 / Table and time-series profile",
        body="\n\n".join("\n".join(_file_lines(file)) for file in assessment.files),
    )
