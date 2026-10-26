# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project measured column rules into quality dimensions and an offline report."""

from datakeel.core.standard_history_models import StandardsReport
from datakeel.core.standard_reporting_models import (
    StandardDimension,
    StandardQualityIssue,
    StandardsGrade,
    StandardsQuality,
)
from datakeel.quality.models import ChapterView, ReportView

_DIMENSIONS = {
    "completeness": ("required",),
    "consistency": ("type", "length", "precision", "unit", "sensitivity"),
    "distribution": ("code_list", "range", "pattern"),
}
_WEIGHTS = {"completeness": 30.0, "consistency": 40.0, "distribution": 30.0}
_EXCELLENT = 90
_GOOD = 75
_FAIR = 60


def score_standards(report: StandardsReport) -> StandardsQuality:
    """Score evaluated column rules equally; unknown rules never receive passing credit."""
    dimensions: dict[str, StandardDimension] = {}
    issues: list[StandardQualityIssue] = []
    for name, rules in _DIMENSIONS.items():
        checked = sum(rule in rules for check in report.checks for rule in check.checked_rules)
        failures = [
            (check.column_id, violation)
            for check in report.checks
            for violation in check.violations
            if violation.rule in rules
        ]
        dimensions[name] = StandardDimension(
            score=round(100 * (checked - len(failures)) / checked, 2) if checked else None,
            checked_rules=checked,
            failed_rules=len(failures),
            violation_count=sum(item.count for _, item in failures),
            weight=_WEIGHTS[name] if checked else 0,
        )
        issues.extend(
            StandardQualityIssue(
                dimension=name,
                column_id=column,
                rule=item.rule,
                count=item.count,
                message=item.message,
            )
            for column, item in failures
        )
    measured = [item for item in dimensions.values() if item.score is not None]
    weight = sum(item.weight for item in measured)
    total = (
        round(sum((item.score or 0) * item.weight for item in measured) / weight, 2)
        if weight
        else None
    )
    return StandardsQuality(
        dimensions=dimensions,
        total=total,
        grade=_grade(total),
        column_count=len(report.profiles),
        mapped_columns=len(report.mappings),
        fully_checked_columns=sum(check.fully_checked for check in report.checks),
        skipped_rules=sum(len(check.skipped_rules) for check in report.checks),
        issues=tuple(issues),
    )


def _grade(total: float | None) -> StandardsGrade:
    if total is None:
        return "unmeasured"
    if total >= _EXCELLENT:
        return "excellent"
    if total >= _GOOD:
        return "good"
    return "fair" if total >= _FAIR else "poor"


def standards_report(report: StandardsReport) -> ReportView:
    """Render aggregate coverage, scored checks and redacted evidence without a model call."""
    quality = score_standards(report)
    coverage = report.coverage.overall
    score = f"{quality.total}/100" if quality.total is not None else "unmeasured"
    chapters = [
        ChapterView(
            title="数据标准 / Data standards",
            body=(
                f"Columns: {coverage.total_columns}; "
                f"confirmed mappings: {coverage.mapped_columns}; "
                f"coverage: {coverage.coverage:.2%}; mapped compliance: {coverage.compliance:.2%}."
            ),
        ),
        ChapterView(
            title="质量评分 / Quality",
            body=(
                f"Standards score: {score} ({quality.grade}). "
                "Each evaluated column rule has equal weight within its dimension. "
                "Dimension weights: completeness 30, consistency 40, distribution 30; "
                f"unmeasured dimensions are excluded. Skipped rules: {quality.skipped_rules}."
            ),
        ),
        ChapterView(title="违规证据 / Violations", body=_violations(report)),
        ChapterView(
            title="治理建议 / Next steps",
            body=(
                "Review mapping candidates before confirming them through controlled actions. "
                "Resolve reported constraints and collect missing profiling evidence. "
                "Counts describe the recorded checked population, not unobserved rows."
            ),
        ),
    ]
    baseline = "\n\n".join(f"## {chapter.title}\n\n{chapter.body}" for chapter in chapters)
    verification = (
        f"Rule evidence: {len(report.checks)} mapped columns checked; "
        f"{len(quality.issues)} failed rules; {quality.skipped_rules} skipped rules."
    )
    return ReportView(
        chapters=chapters,
        body=f"{baseline}\n\n{verification}",
        baseline=baseline,
        baseline_verification=verification,
        fallback=False,
        source="baseline",
    )


def _violations(report: StandardsReport) -> str:
    lines = [
        f"- {check.column_id} → {check.standard_code}: {item.rule}; count={item.count}; "
        f"samples={', '.join(item.samples) or 'none'}; {item.message}"
        for check in report.checks
        for item in check.violations
    ]
    return "\n".join(lines) or "No violations in evaluated rules; skipped rules remain unverified."
