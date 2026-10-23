# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow-owned recovery authorization, separate replay keys and interruption audit."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.recovery import approval_error
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.models import new_id, utcnow
from datakeel.core.workflow_models import WorkflowAudit
from datakeel.storage.action_store import locked_plan
from datakeel.storage.approval_evidence import read_approval
from datakeel.storage.database import Database
from datakeel.storage.workflow_rows import WorkflowAuditRow, WorkflowResumeRow, WorkflowStepRow
from datakeel.storage.workflow_store import get_run, locked_run


def _audit(session: Session, run_id: str, plan_id: str | None, kind: str, reason: str) -> None:
    session.add(
        WorkflowAuditRow(
            id=new_id(),
            run_id=run_id,
            plan_id=plan_id,
            kind=kind,
            reason=reason,
            created_at=utcnow().timestamp(),
        )
    )


def authorize_resume(db: Database, run_id: str, plan_id: str, pending_plan_id: str) -> ActionPlan:
    """Commit rejection evidence before raising, independently of action execution checks."""
    run = get_run(db, run_id)
    plan: ActionPlan | None = None
    reason = "plan_not_pending"
    with db.session() as session:
        db.lock_writes(session)
        locked_run(session, run_id)
        if run.status == "PAUSED" and plan_id == pending_plan_id:
            try:
                _, plan = locked_plan(session, plan_id)
            except NotFoundError:
                reason = "plan_not_in_workflow"
            else:
                reason = (
                    "actor_mismatch"
                    if plan.actor != "local"
                    else approval_error(plan, read_approval(session, plan_id), run_id, utcnow())
                )
                if reason == "plan_not_in_session":
                    reason = "plan_not_in_workflow"
        _audit(
            session,
            run_id,
            plan_id,
            "RESUME_DENIED" if reason else "RESUME_AUTHORIZED",
            reason or "approved_record",
        )
        session.commit()
    if reason or plan is None:
        msg = f"Workflow resume denied: {reason}"
        raise AuthorizationError(msg)
    return plan


def begin_resume(db: Database, run_id: str, request: ResumeInput) -> bool:
    """Return whether the same signed resume already completed without executing again."""
    with db.session() as session:
        db.lock_writes(session)
        locked_run(session, run_id)
        previous = session.get(WorkflowResumeRow, (run_id, request.idempotency_key))
        if previous is not None:
            if previous.plan_id != request.plan_id:
                msg = "Idempotency key is bound to a different resume plan"
                raise ConflictError(msg)
            return previous.completed
        session.add(
            WorkflowResumeRow(
                run_id=run_id,
                idempotency_key=request.idempotency_key,
                plan_id=request.plan_id,
                completed=False,
            )
        )
        session.commit()
        return False


def finish_resume(db: Database, run_id: str, request: ResumeInput) -> None:
    """Mark a fully delivered resume for durable idempotent replay."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(WorkflowResumeRow, (run_id, request.idempotency_key))
        if row is None:
            msg = "Workflow resume was not started"
            raise NotFoundError(msg)
        row.completed = True
        session.commit()


def interrupt_run(db: Database, run_id: str, reason: str) -> None:
    """Stop abandoned non-paused execution without permitting arbitrary mid-run replay."""
    with db.session() as session:
        db.lock_writes(session)
        row = locked_run(session, run_id)
        if row.status not in {"PENDING", "RUNNING", "PAUSED"}:
            return
        row.status, row.error = "INTERRUPTED", reason
        row.pending_plan_id = None
        row.updated_at = utcnow().timestamp()
        for step in session.scalars(
            select(WorkflowStepRow).where(
                WorkflowStepRow.run_id == run_id, WorkflowStepRow.status.in_(["RUNNING", "PAUSED"])
            )
        ):
            step.status, step.error = "FAILED", reason
            step.finished_at = utcnow().timestamp()
        _audit(session, run_id, None, "INTERRUPTED", reason)
        session.commit()


def list_audit(db: Database, run_id: str) -> list[WorkflowAudit]:
    """Expose persisted resume denials, approval checks and abandoned-stream evidence."""
    get_run(db, run_id)
    with db.session() as session:
        rows = session.scalars(
            select(WorkflowAuditRow)
            .where(WorkflowAuditRow.run_id == run_id)
            .order_by(WorkflowAuditRow.created_at, WorkflowAuditRow.id)
        )
        return [
            WorkflowAudit.model_validate(
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "plan_id": row.plan_id,
                    "kind": row.kind,
                    "reason": row.reason,
                    "created_at": datetime.fromtimestamp(row.created_at, UTC),
                }
            )
            for row in rows
        ]
