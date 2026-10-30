# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reconcile asynchronous action runs from authoritative durable task outcomes."""

from sqlalchemy import select

from datakeel.actions.models import WorkerDecision
from datakeel.actions.receipts import receipt
from datakeel.core.errors import DatakeelError
from datakeel.core.models import AssetRef, utcnow
from datakeel.storage.action_locks import lock_action_targets
from datakeel.storage.action_planning import verify_target_state
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.action_store import audit, locked_plan, publish
from datakeel.storage.database import Database, TaskRow, VersionRow


def start_task_run(db: Database, task_id: str) -> WorkerDecision:
    """Revalidate frozen targets before each leased action shard actually starts."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalar(
            select(ActionRunRow).where(ActionRunRow.task_id == task_id).with_for_update()
        )
        if row is None:
            return WorkerDecision()
        _plan_row, plan = locked_plan(session, row.plan_id)
        try:
            verify_target_state(session, plan)
        except DatakeelError as error:
            audit(session, plan, "WORKER_AUTHORIZE", "FAILED", str(error))
            session.commit()
            return WorkerDecision(allowed=False, error=str(error))
        row.status = "RUNNING"
        session.commit()
        return WorkerDecision()


def reconcile_runs(db: Database) -> int:
    """Publish exactly one action receipt after a worker task reaches terminal state."""
    completed = 0
    with db.session() as session:
        lock_action_targets(db, session)
        rows = list(
            session.scalars(
                select(ActionRunRow)
                # A cloud prelabel run is RUNNING without a worker task; its caller closes it.
                .where(
                    ActionRunRow.status.in_(["QUEUED", "RUNNING"]),
                    ActionRunRow.task_id.is_not(None),
                )
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            task = session.get(TaskRow, row.task_id)
            if task is None or task.state not in {"COMPLETED", "FAILED", "CANCELLED"}:
                continue
            plan_row, plan = locked_plan(session, row.plan_id)
            version = session.scalar(select(VersionRow).where(VersionRow.task_id == task.id))
            error = task.error or "Pipeline failed" if task.state != "COMPLETED" else None
            outputs = [AssetRef(asset_type="task", asset_id=task.id)]
            if task.datasheet_job_id is not None:
                outputs.append(
                    AssetRef(
                        asset_type="datasheet",
                        asset_id=task.datasheet_job_id,
                        version=task.input_version_id,
                    )
                )
            if version is not None:
                outputs.append(
                    AssetRef(asset_type="version", asset_id=version.id, version=version.id)
                )
            event = receipt(plan, row.id, outputs, error=error)
            row.status = "FAILED" if error else "SUCCEEDED"
            row.error, row.receipt = error, event.model_dump(mode="json")
            row.completed_at = utcnow().timestamp()
            if error:
                plan_row.status = "FAILED"
            audit(session, plan, "WORKER", row.status, error or "")
            publish(session, event)
            completed += 1
        session.commit()
    return completed
