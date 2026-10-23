# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional workflow starts, durable step outputs and read-only run projections."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.core.workflow_models import (
    WorkflowCreation,
    WorkflowRecord,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from datakeel.storage.database import Database
from datakeel.storage.workflow_rows import WorkflowRunRow, WorkflowStepRow


def locked_run(session: Session, run_id: str) -> WorkflowRunRow:
    """Lock one workflow identity inside storage or report a missing run."""
    row = session.scalar(
        select(WorkflowRunRow).where(WorkflowRunRow.id == run_id).with_for_update()
    )
    if row is None:
        msg = "Workflow run not found"
        raise NotFoundError(msg)
    return row


def _step_view(row: WorkflowStepRow) -> WorkflowStep:
    return WorkflowStep.model_validate(
        {
            "id": row.id,
            "type": row.type,
            "status": row.status,
            "output": row.output,
            "error": row.error,
            "plan_id": row.plan_id,
            "started_at": datetime.fromtimestamp(row.started_at, UTC) if row.started_at else None,
            "finished_at": datetime.fromtimestamp(row.finished_at, UTC)
            if row.finished_at
            else None,
        }
    )


def _view(session: Session, row: WorkflowRunRow) -> WorkflowRun:
    steps = session.scalars(
        select(WorkflowStepRow)
        .where(WorkflowStepRow.run_id == row.id)
        .order_by(WorkflowStepRow.ordinal)
    )
    return WorkflowRun.model_validate(
        {
            "id": row.id,
            "workflow_id": row.workflow_id,
            "status": row.status,
            "inputs": row.inputs,
            "steps": [_step_view(step) for step in steps],
            "pending_plan_id": row.pending_plan_id,
            "error": row.error,
            "created_at": datetime.fromtimestamp(row.created_at, UTC),
            "updated_at": datetime.fromtimestamp(row.updated_at, UTC),
        }
    )


def create_run(db: Database, creation: WorkflowCreation) -> tuple[WorkflowRun, bool]:
    """Bind one start key to its validated input, preserving the first frozen definition."""
    encoded = json.dumps(
        [creation.workflow_id, creation.request.inputs.root], sort_keys=True, ensure_ascii=False
    )
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    with db.session() as session:
        db.lock_writes(session)
        previous = session.scalar(
            select(WorkflowRunRow).where(
                WorkflowRunRow.idempotency_key == creation.request.idempotency_key
            )
        )
        if previous is not None:
            if previous.request_digest != digest:
                msg = "Idempotency key is bound to different workflow inputs"
                raise ConflictError(msg)
            return _view(session, previous), False
        row = WorkflowRunRow(
            id=new_id(),
            workflow_id=creation.workflow_id,
            idempotency_key=creation.request.idempotency_key,
            request_digest=digest,
            definition=creation.definition.root,
            inputs=creation.request.inputs.root,
            status="PENDING",
            created_at=utcnow().timestamp(),
            updated_at=utcnow().timestamp(),
        )
        session.add(row)
        session.flush()
        for ordinal, step in enumerate(creation.steps):
            session.add(
                WorkflowStepRow(
                    run_id=row.id, id=step.id, type=step.type, ordinal=ordinal, status="PENDING"
                )
            )
        session.flush()
        result = _view(session, row)
        session.commit()
        return result, True


def get_run(db: Database, run_id: str) -> WorkflowRun:
    """Read one run with declared steps in definition order."""
    return get_record(db, run_id).run


def get_record(db: Database, run_id: str) -> WorkflowRecord:
    """Load the original definition, never a newly edited contract, for recovery."""
    with db.session() as session:
        row = session.get(WorkflowRunRow, run_id)
        if row is None:
            msg = "Workflow run not found"
            raise NotFoundError(msg)
        return WorkflowRecord(
            run=_view(session, row),
            definition=JsonDocument(row.definition),
            request_digest=row.request_digest,
        )


def list_runs(db: Database) -> list[WorkflowRun]:
    """List newest workflow runs first without exposing checkpoint internals."""
    with db.session() as session:
        return [
            _view(session, row)
            for row in session.scalars(
                select(WorkflowRunRow).order_by(WorkflowRunRow.created_at.desc(), WorkflowRunRow.id)
            )
        ]


def save_step(db: Database, run_id: str, step: WorkflowStep) -> None:
    """Commit one step's outcome independently of its following checkpoint."""
    with db.session() as session:
        db.lock_writes(session)
        run = locked_run(session, run_id)
        row = session.get(WorkflowStepRow, (run_id, step.id))
        if row is None:
            msg = "Workflow step not found"
            raise NotFoundError(msg)
        row.status, row.output, row.error, row.plan_id = (
            step.status,
            step.output,
            step.error,
            step.plan_id,
        )
        row.started_at = step.started_at.timestamp() if step.started_at else None
        row.finished_at = step.finished_at.timestamp() if step.finished_at else None
        run.updated_at = utcnow().timestamp()
        session.commit()


def set_status(
    db: Database,
    run_id: str,
    status: WorkflowStatus,
    *,
    error: str | None = None,
    plan_id: str | None = None,
) -> None:
    """Publish terminal or paused state and close skipped branches on success."""
    with db.session() as session:
        db.lock_writes(session)
        row = locked_run(session, run_id)
        row.status, row.error, row.pending_plan_id = status, error, plan_id
        row.updated_at = utcnow().timestamp()
        if status == "SUCCEEDED":
            for step in session.scalars(
                select(WorkflowStepRow).where(
                    WorkflowStepRow.run_id == run_id, WorkflowStepRow.status == "PENDING"
                )
            ):
                step.status = "SKIPPED"
        session.commit()
