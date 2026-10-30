# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Finish the slow part of an executed plan after its transaction committed.

Today that is a cloud prelabel run: the plan's transaction only claimed the project's run slot
and froze its targets, estimate and thresholds. Here the model calls run outside any
transaction, each batch is saved on its own, and one last short transaction closes the run,
writes its audit lines and publishes the action's single receipt. The caller still gets the
finished action run back, so executing stays synchronous for every client.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.actions.policy import digest
from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.actions.receipts import receipt
from datakeel.core.models import utcnow
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.storage.action_locks import lock_row_writes
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.action_store import audit, publish, run_view
from datakeel.storage.database import Database
from datakeel.storage.production_ai_audit import audit_prelabel_run
from datakeel.storage.production_cloud_runner import Ledger, finish_run, label_remaining
from datakeel.storage.production_prelabel_runs import prelabel_outputs

logger = logging.getLogger(__name__)
ABANDONED = "Abandoned: another run took over this project's prelabel slot"


def _settle(
    session: Session,
    plan: ActionPlan,
    action_run_id: str,
    run: PrelabelRun,
    error: str | None,
) -> ActionRun:
    row = session.scalar(
        select(ActionRunRow).where(ActionRunRow.id == action_run_id).with_for_update()
    )
    if row is None:
        message = "Deferred action run not found"
        raise LookupError(message)
    if error is None and run.status == "abandoned":
        error = ABANDONED
    if error is None:
        audit_prelabel_run(session, plan, run)
        event = receipt(plan, row.id, prelabel_outputs(run))
    else:
        event = receipt(plan, row.id, [], error=error)
        plan_row = session.get(ActionPlanRow, plan.id)
        if plan_row is not None:
            plan_row.status = "FAILED"
    details = run.model_dump(mode="json")
    event = event.model_copy(update={"quality": {**event.quality, "details": details}})
    row.status = "FAILED" if error else "SUCCEEDED"
    row.error, row.receipt = error, event.model_dump(mode="json")
    row.completed_at = utcnow().timestamp()
    audit(session, plan, "DEFERRED", row.status, error or digest(details))
    publish(session, event)
    session.flush()
    return run_view(row)


def complete_deferred(
    db: Database, plan: ActionPlan, action_run_id: str, deferred_id: str
) -> ActionRun:
    """Run the deferred calls, then close the run and publish the action's receipt once."""
    params = RunPrelabelParams.model_validate(plan.canonical_params)
    ledger: Ledger | None = None
    stopped = None
    error: str | None = None
    try:
        ledger, stopped = label_remaining(db, params, deferred_id)
    except Exception as exc:
        logger.exception("Deferred action work failed", extra={"action_id": plan.id})
        error = f"{type(exc).__name__}: {exc}"
    with db.session() as session:
        lock_row_writes(db, session)
        run = finish_run(session, deferred_id, ledger, stopped)
        view = _settle(session, plan, action_run_id, run, error)
        session.commit()
    return view
