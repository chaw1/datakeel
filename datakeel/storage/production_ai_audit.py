# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write the action audit line for every submission the AI pre-review exempted from review."""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.core.prelabel_models import AIReview
from datakeel.storage.action_store import audit
from datakeel.storage.production_ai_rows import latest_reviews


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
