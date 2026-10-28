# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score recorded column and interval measurements without rereading sources."""

from collections import defaultdict

from datakeel.core.models import FileItem
from datakeel.operators.table.models import TableProfile
from datakeel.operators.timeseries.models import (
    AnomalySummary,
    GapsSummary,
    OrderSummary,
    SeriesIssue,
    SeriesSummary,
    TimestampSummary,
    UnitSummary,
)
from datakeel.quality.models import IssueView
from datakeel.quality.tabular_models import (
    ProfileColumnBrief,
    TabularAssessment,
    TabularDimension,
    TabularFileAssessment,
    TabularFinding,
)

DIMENSIONS: tuple[TabularDimension, ...] = (
    "completeness",
    "consistency",
    "uniqueness",
    "distribution",
)
SUMMARIES: dict[str, type[SeriesSummary]] = {
    "timestamp_normalize": TimestampSummary,
    "order_dedup": OrderSummary,
    "gaps": GapsSummary,
    "anomaly": AnomalySummary,
    "unit_check": UnitSummary,
}


def _dimension(rule: str) -> TabularDimension:
    if rule in {"sampling_gap", "invalid_timestamp", "null_values", "empty_table"}:
        return "completeness"
    if rule in {"duplicate_timestamp", "duplicate"}:
        return "uniqueness"
    if rule in {"stuck_value", "jump", "robust_z", "out_of_range"}:
        return "distribution"
    return "consistency"


def _finding(file: FileItem, issue: SeriesIssue) -> TabularFinding:
    return TabularFinding(
        dimension=_dimension(issue.rule),
        rule=issue.rule,
        file_id=file.id,
        filename=file.filename,
        column=issue.column,
        device=issue.device,
        rows=issue.rows,
        start_ms=issue.start_ms,
        end_ms=issue.end_ms,
        threshold=issue.threshold,
        window=issue.window,
        detail=issue.detail,
        recommendation=issue.recommendation,
    )


def _summaries(file: FileItem) -> tuple[SeriesSummary, ...]:
    raw: object = file.metadata.get("timeseries")
    if not isinstance(raw, dict):
        return ()
    return tuple(model.model_validate(raw[key]) for key, model in SUMMARIES.items() if key in raw)


def _profile_findings(file: FileItem, profile: TableProfile) -> tuple[TabularFinding, ...]:
    return tuple(
        TabularFinding(
            dimension=_dimension(finding.code),
            rule=finding.code,
            file_id=file.id,
            filename=file.filename,
            column=finding.column or "[table]",
            rows=finding.row_numbers,
            detail=finding.detail,
            recommendation=finding.suggested_action,
        )
        for finding in profile.findings
    )


def _file_assessment(file: FileItem) -> TabularFileAssessment | None:
    summaries = _summaries(file)
    profile_raw: object = file.metadata.get("table_profile")
    profile = TableProfile.model_validate(profile_raw) if profile_raw is not None else None
    if profile is None and not summaries:
        return None
    row_count = max((item.row_count for item in summaries), default=0)
    if profile is not None:
        row_count = max(row_count, profile.row_count)
    findings = tuple(_finding(file, issue) for item in summaries for issue in item.issues)
    findings += _profile_findings(file, profile) if profile else ()
    scores = _scores(findings, row_count)
    if profile is not None and not profile.row_count:
        scores["completeness"] = 0
    if profile and profile.columns:
        missing = sum(column.null_count for column in profile.columns)
        scores["completeness"] = min(
            scores["completeness"],
            100 * (1 - missing / max(1, profile.row_count * len(profile.columns))),
        )
    missing_samples = sum(
        interval.missing_samples
        for item in summaries
        if isinstance(item, GapsSummary)
        for interval in item.intervals
    )
    scores["completeness"] = min(
        scores["completeness"], 100 * row_count / max(1, row_count + missing_samples)
    )
    return TabularFileAssessment(
        file_id=file.id,
        filename=file.filename,
        row_count=row_count,
        scores=scores,
        columns=tuple(
            ProfileColumnBrief(
                name=column.name,
                inferred_type=column.inferred_type,
                null_rate=column.null_rate,
                unique_rate=column.unique_rate,
                pii_kinds=column.pii_kinds,
            )
            for column in profile.columns
        )
        if profile
        else (),
        findings=findings,
        anomaly_intervals=sum(
            item.anomaly_intervals for item in summaries if isinstance(item, AnomalySummary)
        ),
        total_gap_ms=sum(item.total_gap_ms for item in summaries if isinstance(item, GapsSummary)),
    )


def _scores(findings: tuple[TabularFinding, ...], row_count: int) -> dict[TabularDimension, float]:
    affected: dict[TabularDimension, set[int]] = defaultdict(set)
    for finding in findings:
        if finding.rule not in {"suspected_pii", "null_values", "sampling_gap"}:
            affected[finding.dimension].update(finding.rows)
    return {
        dimension: max(0, 100 * (1 - len(affected[dimension]) / max(1, row_count)))
        for dimension in DIMENSIONS
    }


def assess_tables(files: list[FileItem]) -> TabularAssessment:
    """Average per-file rule coverage so a long table cannot dominate unrelated assets."""
    assessments = tuple(item for file in files if (item := _file_assessment(file)) is not None)
    return TabularAssessment(
        files=assessments,
        scores={
            dimension: 100
            - sum(100 - item.scores[dimension] for item in assessments) / max(1, len(files))
            for dimension in DIMENSIONS
        },
    )


def table_issues(assessment: TabularAssessment) -> tuple[IssueView, ...]:
    """Expose every column and interval reason through the existing quality issue list."""
    return tuple(
        IssueView(
            dimension=finding.dimension,
            severity="warning",
            code=finding.rule,
            message=(
                f"{finding.filename}: {finding.column} [{finding.device or 'all rows'}] "
                f"rows {list(finding.rows[:12])} ({len(finding.rows)} recorded); "
                f"UTC ms {finding.start_ms}..{finding.end_ms}; "
                f"{finding.detail}. {finding.recommendation}"
            ),
        )
        for file in assessment.files
        for finding in file.findings
    )
