# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed action persistence helpers inside caller-owned transactions."""

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ActionRun, PlanStatus
from datakeel.core.errors import NotFoundError
from datakeel.core.models import LineageEvent
from datakeel.storage.action_rows import ActionAuditRow, ActionPlanRow, ActionRunRow
from datakeel.storage.database import Database, OutboxRow
from datakeel.storage.events import append_event


def locked_plan(session: Session, plan_id: str) -> tuple[ActionPlanRow, ActionPlan]:
    """Lock the one-use plan before checking policy or consuming approval."""
    row = session.scalar(select(ActionPlanRow).where(ActionPlanRow.id == plan_id).with_for_update())
    if row is None:
        msg = "Action plan not found"
        raise NotFoundError(msg)
    plan = ActionPlan.model_validate(row.payload)
    return row, plan.model_copy(update={"status": cast("PlanStatus", row.status)})


def run_view(row: ActionRunRow) -> ActionRun:
    """Convert a persisted execution into its immutable public response."""
    return ActionRun.model_validate(
        {
            "id": row.id,
            "plan_id": row.plan_id,
            "action_type": row.action_type,
            "status": row.status,
            "created_at": datetime.fromtimestamp(row.created_at, UTC),
            "completed_at": datetime.fromtimestamp(row.completed_at, UTC)
            if row.completed_at
            else None,
            "task_id": row.task_id,
            "receipt": row.receipt,
            "error": row.error,
            "reason": row.error if row.status == "DENIED" else None,
        }
    )


def audit(session: Session, plan: ActionPlan, phase: str, status: str, detail: str = "") -> None:
    """Record actor-attributed policy evidence in the business transaction."""
    session.add(
        ActionAuditRow(
            plan_id=plan.id,
            action_type=plan.action_type,
            actor=plan.actor,
            session_id=plan.session_id,
            phase=phase,
            status=status,
            detail={"message": detail},
        )
    )


def publish(session: Session, event: LineageEvent) -> None:
    """Persist a receipt and a replayable outbox in the same transaction."""
    append_event(session, event)
    session.add(
        OutboxRow(idempotency_key=event.idempotency_key, payload=event.model_dump(mode="json"))
    )


def list_runs(db: Database) -> list[ActionRun]:
    """List durable attempts, including rejected and failed executions."""
    with db.session() as session:
        return [
            run_view(row)
            for row in session.scalars(
                select(ActionRunRow).order_by(ActionRunRow.created_at.desc())
            )
        ]


def list_approvals(db: Database) -> list[ActionPlan]:
    """List plans that still require an explicit human approval decision."""
    with db.session() as session:
        plans = [
            ActionPlan.model_validate(row.payload)
            for row in session.scalars(
                select(ActionPlanRow)
                .where(ActionPlanRow.status == "PREPARED")
                .order_by(ActionPlanRow.created_at)
            )
        ]
        return [plan for plan in plans if plan.requires_approval]


def get_plan(db: Database, plan_id: str) -> ActionPlan:
    """Read one plan with its current approval/execution status."""
    with db.session() as session:
        return locked_plan(session, plan_id)[1]
