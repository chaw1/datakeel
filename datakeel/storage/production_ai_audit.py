# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit lines for model pass-through submissions and for AI pre-review exemptions."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.core.prelabel_models import AIReview, ConfidenceThresholds
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import AnnotationRevision
from datakeel.storage.action_rows import ApprovalRow
from datakeel.storage.action_store import audit
from datakeel.storage.production_ai_rows import latest_reviews
from datakeel.storage.production_rows import ProductionRevisionRow

DIRECT_SUBMISSION = "模型高置信度直通 / Model high-confidence pass-through"


def audit_pass_through_relaxed(
    session: Session,
    plan: ActionPlan,
    before: ConfidenceThresholds,
    after: ConfidenceThresholds,
) -> None:
    """Name the old and new pass-through bar and the person who signed the change."""
    approver = session.scalar(
        select(ApprovalRow.actor).where(
            ApprovalRow.plan_id == plan.id, ApprovalRow.status == "APPROVED"
        )
    )
    signer = approver or "-"
    old_zh, old = (
        (f"高档 {before.high:.2f}", f"high {before.high:.2f}")
        if before.pass_through and before.high is not None
        else ("未开启（冷启动）", "off (cold start)")  # noqa: RUF001  # Chinese punctuation is intended.
    )
    new = f"{after.high:.2f}" if after.high is not None else "-"
    audit(
        session,
        plan,
        "PASS_THROUGH",
        "RELAXED",
        f"放宽高置信度直通：{old_zh} → 高档 {new}，签批人 {signer} / "  # noqa: RUF001  # Chinese punctuation is intended.
        f"High-confidence pass-through relaxed: {old} -> high {new}, approved by {signer}",
    )


def audit_exemptions(session: Session, plan: ActionPlan, reviews: Iterable[AIReview]) -> None:
    """Record the fixed exemption wording with the task, sampling ratio and risk score."""
    for review in reviews:
        if review.decision == "exempt":
            audit(
                session,
                plan,
                "AI_PREREVIEW",
                "EXEMPTED",
                f"task={review.task_id}; revision={review.revision_id}; {review.note}",
            )


def audit_run_exemptions(session: Session, plan: ActionPlan, task_ids: tuple[str, ...]) -> None:
    """Audit the exemptions this action just produced for the given tasks' newest reviews."""
    audit_exemptions(session, plan, latest_reviews(session, task_ids).values())


def audit_pass_through(session: Session, plan: ActionPlan, run: PrelabelRun) -> tuple[str, ...]:
    """Write one fixed bilingual line per submitted draft: model, confidence, bar and trigger.

    Returns the submitted task ids so their pre-review exemptions are audited next.
    """
    submitted: list[str] = []
    for tier in run.tiers:
        row = session.get(ProductionRevisionRow, tier.revision_id) if tier.revision_id else None
        revision = AnnotationRevision.model_validate(row.payload) if row is not None else None
        if tier.routed != "submitted" or revision is None or revision.pass_through is None:
            continue
        given = revision.pass_through
        submitted.append(tier.task_id)
        audit(
            session,
            plan,
            "PRELABEL",
            "PASS_THROUGH",
            f"{DIRECT_SUBMISSION}: task={tier.task_id}; revision={revision.id}; "
            f"model={given.model_id} ({revision.model_name} {revision.model_version}); "
            f"confidence={given.confidence:.3f}; high={given.high:.3f}; "
            f"low={given.low if given.low is None else format(given.low, '.3f')}; "
            f"thresholds={given.threshold_source} from {given.reviewed_objects} objects; "
            f"triggered_by={given.triggered_by}",
        )
    return tuple(submitted)


def audit_prelabel_run(session: Session, plan: ActionPlan, run: PrelabelRun) -> None:
    """Audit every pass-through of a finished run, then the exemptions its reviews granted."""
    audit_run_exemptions(session, plan, audit_pass_through(session, plan, run))
