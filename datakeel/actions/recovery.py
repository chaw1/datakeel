# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure signed-approval validation shared by conversation and workflow recovery."""

from datetime import datetime

from datakeel.actions.models import ActionPlan
from datakeel.actions.policy import plan_digest
from datakeel.core.models import BoundaryModel


class ApprovalEvidence(BoundaryModel):
    """Project only the durable approval and execution facts needed by recovery policy."""

    status: str
    actor: str
    plan_digest: str
    consumed: bool
    run_status: str | None = None


def approval_error(
    plan: ActionPlan, approval: ApprovalEvidence | None, session_id: str, now: datetime
) -> str:
    """Return a denial reason without querying storage or trusting a resume payload."""
    if plan.session_id != session_id:
        return "plan_not_in_session"
    if plan.expires_at <= now:
        return "expired"
    if approval is None:
        return "no_approval"
    checks = [
        (approval.status != "APPROVED" or not plan.requires_approval, "approval_rejected"),
        (approval.actor != plan.actor, "actor_mismatch"),
        (
            approval.plan_digest != plan.plan_digest or plan_digest(plan) != plan.plan_digest,
            "digest_mismatch",
        ),
        (approval.consumed and approval.run_status is None, "approval_consumed"),
    ]
    if reason := next((reason for failed, reason in checks if failed), ""):
        return reason
    valid = plan.status == "APPROVED" or (
        (plan.status == "EXECUTED" and approval.run_status in {"QUEUED", "RUNNING", "SUCCEEDED"})
        or (plan.status == "FAILED" and approval.run_status == "FAILED")
    )
    return "" if valid else "approval_rejected"
