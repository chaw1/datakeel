# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist human approvals bound to one unchanged action plan."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ApprovalDecision
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.storage.action_access import authorize_plans_in_session
from datakeel.storage.action_planning import verify_plan
from datakeel.storage.action_rows import ApprovalRow
from datakeel.storage.action_store import audit, locked_plan
from datakeel.storage.database import Database


def approve_plan(
    db: Database,
    plan_id: str,
    decision: ApprovalDecision,
    *,
    access: AccessContext | None = None,
) -> ActionPlan:
    """Approve or reject the exact displayed plan once, before it expires."""
    with db.session() as session:
        db.lock_writes(session)
        row, plan = locked_plan(session, plan_id)
        verify_plan(session, plan, decision.plan_digest, decision.actor)
        if plan.status != "PREPARED":
            msg = "Action plan already has a decision or execution"
            raise ConflictError(msg)
        if not plan.requires_approval:
            msg = "Reversible local actions do not require approval"
            raise ConflictError(msg)
        authorize_plans_in_session(session, (plan,), access, actor=decision.actor)
        status = "APPROVED" if decision.approve else "REJECTED"
        session.add(
            ApprovalRow(
                plan_id=plan.id,
                plan_digest=plan.plan_digest,
                actor=decision.actor,
                status=status,
                reason=decision.reason,
            )
        )
        row.status = status
        audit(session, plan, "APPROVAL", status, decision.reason)
        session.commit()
        return plan.model_copy(update={"status": status})


def consume_approval(session: Session, plan: ActionPlan) -> None:
    """Atomically consume an unchanged approval inside the execution transaction."""
    if plan.status == "REJECTED":
        msg = "Human approval was rejected"
        raise ConflictError(msg)
    if plan.status == "EXECUTED":
        msg = "Action plan was already executed; approval was consumed"
        raise ConflictError(msg)
    approval = session.scalar(
        select(ApprovalRow).where(ApprovalRow.plan_id == plan.id).with_for_update()
    )
    if approval is not None and approval.consumed:
        msg = "Human approval was already consumed"
        raise ConflictError(msg)
    if plan.status not in {"PREPARED", "APPROVED"}:
        msg = "Action plan has failed"
        raise ConflictError(msg)
    if not plan.requires_approval:
        return
    if approval is None or approval.status != "APPROVED":
        msg = "Action requires explicit human approval"
        raise AuthorizationError(msg)
    if approval.plan_digest != plan.plan_digest:
        msg = "Human approval no longer matches the plan"
        raise ConflictError(msg)
    if approval.actor != plan.actor:
        msg = "Human approval actor does not match the prepared plan"
        raise AuthorizationError(msg)
    approval.consumed = True
