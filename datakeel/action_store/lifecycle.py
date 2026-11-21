# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind ordered lifecycle stages and read durable action history."""

import logging
from importlib import import_module
from typing import TYPE_CHECKING, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.declarations import ActionFrame
from datakeel.actions.file_declarations import active_declarations
from datakeel.actions.models import ActionPlan, ActionRun, OperationResult, PlanStatus
from datakeel.actions.parameters import parse_params
from datakeel.actions.receipts import receipt
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, LineageEvent, utcnow
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.action_store import audit, publish, run_view
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


logger = logging.getLogger(__name__)


def get_plans_by_ids(db: Database, plan_ids: "Sequence[str]") -> dict[str, ActionPlan]:
    """Read requested plans and their current statuses without acquiring row locks."""
    if not plan_ids:
        return {}
    with db.session() as session:
        return {
            row.id: ActionPlan.model_validate(row.payload).model_copy(
                update={"status": cast("PlanStatus", row.status)}
            )
            for row in session.scalars(select(ActionPlanRow).where(ActionPlanRow.id.in_(plan_ids)))
        }


def get_runs_by_plan_ids(
    db: Database, plan_ids: "Sequence[str]", *, newest_first: bool = True
) -> dict[str, list[ActionRun]]:
    """Read requested plans' attempts, optionally in oldest-first chain order."""
    found: dict[str, list[ActionRun]] = {identifier: [] for identifier in plan_ids}
    if not plan_ids:
        return found
    statement = select(ActionRunRow).where(ActionRunRow.plan_id.in_(plan_ids))
    if newest_first:
        statement = statement.order_by(ActionRunRow.created_at.desc())
    else:
        statement = statement.order_by(ActionRunRow.created_at, ActionRunRow.id)
    with db.session() as session:
        for row in session.scalars(statement):
            found[row.plan_id].append(run_view(row))
    return found


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


def stage(action: str, phase: str, session: Session, frame: ActionFrame) -> ActionFrame:
    """Resolve the declared stage and preserve typed frame and handler ordering."""
    declaration = active_declarations()[action]
    handlers = declaration.handlers
    names = cast("str | tuple[str, ...]", getattr(handlers, phase))
    for name in names if isinstance(names, tuple) else (names,):
        handler = getattr(import_module(handlers.module), name, None)
        if not callable(handler):
            msg = "Missing declared lifecycle handler"
            raise ValidationError(msg)
        value = cast("Callable[[Session, ActionFrame], object]", handler)(session, frame)
        if not isinstance(value, ActionFrame):
            msg = "Lifecycle handler returned an invalid frame"
            raise ValidationError(msg)
        frame = value
    return frame


def prepared(action: str, session: Session, frame: ActionFrame) -> ActionFrame:
    """Run the declared prepare stages and enforce the static approval floor."""
    declaration = active_declarations()[action]
    for phase in ("prepare", "manifest", "references", "snapshot", "impact"):
        prior = frame
        frame = stage(action, phase, session, frame)
        frame = frame.model_copy(
            update={
                "reversible": prior.reversible and frame.reversible,
                "external": prior.external or frame.external,
            }
        )
    return frame.model_copy(
        update={
            "reversible": frame.reversible
            and declaration.reversible
            and declaration.approval.mode == "auto"
        }
    )


def complete(db: Database, plan: ActionPlan, run_id: str, deferred_id: str) -> ActionRun:
    """Complete generated deferred work and publish one receipt in a short transaction."""
    handlers = active_declarations()[plan.action_type].handlers
    handler = getattr(import_module(handlers.module), handlers.deferred or "", None)
    if not callable(handler):
        msg = "Missing declared deferred handler"
        raise ValidationError(msg)
    error: str | None = None
    result = OperationResult()
    try:
        result = cast("Callable[[Database, ActionPlan, str], OperationResult]", handler)(
            db, plan, deferred_id
        )
    except Exception as failure:
        logger.exception("Declared deferred work failed", extra={"action_id": plan.id})
        error = f"{type(failure).__name__}: {failure}"
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(ActionRunRow, run_id, with_for_update=True)
        if row is None:
            msg = "Deferred action run not found"
            raise ValidationError(msg)
        if row.status != "RUNNING":
            return run_view(row)
        event = declared_receipt(session, plan, run_id, result, error=error)
        row.receipt = event.model_dump(mode="json")
        row.status = "FAILED" if error else "SUCCEEDED"
        row.error = error
        plan_row = session.get(ActionPlanRow, plan.id)
        if error and plan_row is not None:
            plan_row.status = "FAILED"
        row.completed_at = utcnow().timestamp()
        publish(session, event)
        audit(session, plan, "DEFERRED", row.status)
        session.commit()
        return run_view(row)


def declared_receipt(
    session: Session,
    plan: ActionPlan,
    run_id: str,
    result: OperationResult,
    *,
    error: str | None = None,
) -> LineageEvent:
    """Apply the declared terminal hooks without owning commit or publication."""
    if plan.action_type not in active_declarations():
        return receipt(plan, run_id, result.outputs, error=error)
    frame = _frame(plan, result).model_copy(update={"run_id": run_id, "error": error})
    frame = stage(plan.action_type, "completion", session, frame)
    frame = stage(plan.action_type, "receipt", session, frame)
    if frame.event is None:
        msg = "Incomplete action lifecycle frame"
        raise ValidationError(msg)
    if error:
        return frame.event
    return frame.event.model_copy(
        update={"quality": {**frame.event.quality, "details": result.details}}
    )


def rollback(
    db: Database, plan: ActionPlan | None, result: OperationResult | None, *, attempted: bool
) -> None:
    """Release declared resources after rollback, preserving the original failure and audit."""
    if not attempted or plan is None or plan.action_type not in active_declarations():
        return
    try:
        with db.session() as session:
            stage(plan.action_type, "rollback", session, _frame(plan, result))
    except Exception:
        logger.exception("Declared resource rollback failed", extra={"action_id": plan.id})


def _frame(plan: ActionPlan, result: OperationResult | None) -> ActionFrame:
    return ActionFrame(
        params=parse_params(plan.action_type, JsonDocument(plan.canonical_params)),
        plan=plan,
        result=result,
    )
