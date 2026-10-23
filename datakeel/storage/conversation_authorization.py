# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate authoritative recovery approval and retain every rejection independently."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.recovery import approval_error
from datakeel.core.agent_models import ConversationAudit
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.action_store import locked_plan
from datakeel.storage.approval_evidence import read_approval
from datakeel.storage.conversation_rows import ConversationAuditRow
from datakeel.storage.conversation_store import get
from datakeel.storage.database import Database


def _reason(session: Session, plan: ActionPlan, conversation_id: str) -> str:
    reason = approval_error(plan, read_approval(session, plan.id), conversation_id, utcnow())
    return "plan_not_in_conversation" if reason == "plan_not_in_session" else reason


def _audit(session: Session, conversation_id: str, plan_id: str, kind: str, reason: str) -> None:
    session.add(
        ConversationAuditRow(
            id=new_id(),
            conversation_id=conversation_id,
            plan_id=plan_id,
            kind=kind,
            reason=reason,
            created_at=utcnow().timestamp(),
        )
    )


def authorize_resume(
    db: Database, conversation_id: str, plan_id: str, pending_plan_id: str
) -> ActionPlan:
    """Reject forged resume requests before any action dispatch and commit their audit first."""
    conversation = get(db, conversation_id)
    plan: ActionPlan | None = None
    reason = "plan_not_pending"
    with db.session() as session:
        db.lock_writes(session)
        if plan_id == pending_plan_id:
            try:
                _, plan = locked_plan(session, plan_id)
            except NotFoundError:
                reason = "plan_not_in_conversation"
            else:
                reason = (
                    "actor_mismatch"
                    if plan.actor != conversation.actor
                    else _reason(session, plan, conversation_id)
                )
        _audit(
            session,
            conversation_id,
            plan_id,
            "RESUME_DENIED" if reason else "RESUME_AUTHORIZED",
            reason or "approved_record",
        )
        session.commit()
    if reason or plan is None:
        msg = f"Resume denied: {reason}"
        raise AuthorizationError(msg)
    return plan


def record_audit(
    db: Database,
    conversation_id: str,
    plan_id: str,
    kind: Literal["INTERRUPT_INVALIDATED", "CANARY_LEAK", "DELEGATION_DENIED"],
    reason: str,
) -> None:
    """Record replacement of a pause before deleting its disposable checkpoint."""
    with db.session() as session:
        db.lock_writes(session)
        _audit(session, conversation_id, plan_id, kind, reason)
        session.commit()


def list_audit(db: Database, conversation_id: str) -> list[ConversationAudit]:
    """Read recovery policy evidence in creation order through a typed boundary."""
    get(db, conversation_id)
    with db.session() as session:
        rows = session.scalars(
            select(ConversationAuditRow)
            .where(ConversationAuditRow.conversation_id == conversation_id)
            .order_by(ConversationAuditRow.created_at, ConversationAuditRow.id)
        )
        return [
            ConversationAudit.model_validate(
                {
                    "id": row.id,
                    "conversation_id": row.conversation_id,
                    "plan_id": row.plan_id,
                    "kind": row.kind,
                    "reason": row.reason,
                    "created_at": datetime.fromtimestamp(row.created_at, UTC),
                }
            )
            for row in rows
        ]
