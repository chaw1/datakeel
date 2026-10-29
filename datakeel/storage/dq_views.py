# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project stored quality evidence into scores, reports and table status views."""

from sqlalchemy.orm import Session

from datakeel.core.dq_models import DqRule
from datakeel.core.dq_views import DqReport, DqRuleView, DqSummary
from datakeel.quality.dq_report import coverage_text
from datakeel.quality.models import DimensionView, IssueView, QualityView
from datakeel.storage.database import Database
from datakeel.storage.dq_issues import list_issues
from datakeel.storage.dq_reads import list_results
from datakeel.storage.dq_store import get_rule, list_rules


def rule_view(session: Session, rule: DqRule) -> DqRuleView:
    """Read the latest result of the current definition, excluding stale revisions."""
    results = list_results(session, rule.id, 1, revision=rule.revision)
    return DqRuleView(rule=rule, latest_result=results[0] if results else None)


def read_rule_view(db: Database, identifier: str) -> DqRuleView:
    """Read a current definition and its exact revision's observation."""
    with db.session() as session:
        return rule_view(session, get_rule(session, identifier))


def read_rule_views(
    db: Database,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> tuple[DqRuleView, ...]:
    """Filter exact source/table identities without conflating schemas."""
    with db.session() as session:
        return tuple(
            rule_view(session, rule)
            for rule in list_rules(session, source_id)
            if (table is None or rule.target.table == table)
            and (schema_name is None or rule.target.schema_name == schema_name)
        )


def summarize_rules(session: Session, rules: tuple[DqRule, ...]) -> DqSummary:
    """Weight error verdicts twice as much as warnings and exclude missing baselines."""
    views = tuple(rule_view(session, rule) for rule in rules if rule.enabled)
    counts = {"passed": 0, "failed": 0, "error": 0, "baseline_insufficient": 0, "pending": 0}
    numerator = denominator = 0
    for view in views:
        status = view.latest_result.status if view.latest_result else "pending"
        counts[status] += 1
        if status in {"passed", "failed", "error"}:
            weight = 2 if view.rule.severity == "error" else 1
            denominator += weight
            numerator += weight * int(status == "passed")
    identifiers = {rule.id for rule in rules}
    return DqSummary(
        score=round(100 * numerator / denominator, 2) if denominator else None,
        total=len(views),
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["error"],
        baseline_insufficient=counts["baseline_insufficient"],
        pending=counts["pending"],
        rules=views,
        open_issues=sum(
            issue.rule_id in identifiers and issue.status != "resolved"
            for issue in list_issues(session)
        ),
    )


def read_summary(
    db: Database,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> DqSummary:
    """Read monitored quality for all sources or one precisely addressed table."""
    with db.session() as session:
        return summarize_rules(
            session,
            tuple(
                rule
                for rule in list_rules(session, source_id)
                if (table is None or rule.target.table == table)
                and (schema_name is None or rule.target.schema_name == schema_name)
            ),
        )


def read_report(
    db: Database,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> DqReport:
    """Build a deterministic analysis report without constructing any model client."""
    summary = read_summary(db, source_id, table, schema_name)
    score = f"{summary.score}/100" if summary.score is not None else "unmeasured"
    lines = [
        f"Database quality: {score}; active rules: {summary.total}.",
        (
            f"Passed: {summary.passed}; failed: {summary.failed}; errors: {summary.errors}; "
            f"baseline insufficient: {summary.baseline_insufficient}; pending: {summary.pending}."
        ),
    ]
    lines.extend(
        f"- {view.rule.id} ({view.rule.target.table}): "
        f"{view.latest_result.status if view.latest_result else 'pending'}; "
        f"{coverage_text(view.latest_result)}"
        for view in summary.rules
    )
    return DqReport(summary=summary, body="\n".join(lines))


def attach_rule_quality(session: Session, dataset_id: str, quality: QualityView) -> QualityView:
    """Combine associated rule evidence with manifest scoring, preserving absent-rule output."""
    rules = tuple(rule for rule in list_rules(session) if rule.dataset_id == dataset_id)
    if not rules:
        return quality
    summary = summarize_rules(session, rules)
    if summary.score is None:
        return quality.model_copy(update={"rules": summary})
    factor = 0.5 if quality.file_count else 0.0
    dimensions = (
        {
            key: value.model_copy(update={"weight": value.weight * factor})
            for key, value in quality.dimensions.items()
        }
        if quality.file_count
        else {}
    )
    dimensions["database_rules"] = DimensionView(
        score=summary.score,
        weight=100 * (1 - factor),
        details={
            "passed": summary.passed,
            "failed": summary.failed,
            "errors": summary.errors,
            "baseline_insufficient": summary.baseline_insufficient,
            "pending": summary.pending,
        },
    )
    total = round(quality.total * factor + summary.score * (1 - factor), 2)
    thresholds = quality.config.thresholds
    grade = next(
        (name for name in ("excellent", "good", "fair") if total >= thresholds[name]), "poor"
    )
    issues = [
        *(quality.issues if quality.file_count else []),
        *[
            IssueView(
                dimension="database_rules",
                severity="critical" if view.rule.severity == "error" else "warning",
                code="quality_rule_failed",
                message=f"{view.rule.id}: {view.latest_result.status}",
            )
            for view in summary.rules
            if view.latest_result and view.latest_result.status in {"failed", "error"}
        ],
    ]
    return quality.model_copy(
        update={
            "rules": summary,
            "dimensions": dimensions,
            "total": total,
            "grade": grade,
            "issues": issues,
        }
    )
