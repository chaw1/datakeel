# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable optional model jobs and publication inside the existing queue fence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.datasheet_parameters import GenerateDatasheetParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.datasheet_execution import (
    DatasheetCompletion,
    DatasheetFence,
    DatasheetJob,
    DatasheetPrepared,
)
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import AssetRef, new_id
from datakeel.datasheets.validation import validate_sections
from datakeel.storage.database import Database, ShardRow, TaskRow
from datakeel.storage.datasheet_job_rows import DatasheetJobRow
from datakeel.storage.datasheet_store import save_in_session


def _job_view(row: DatasheetJobRow) -> DatasheetJob:
    return DatasheetJob.model_validate({**row.payload, "status": row.status, "error": row.error})


def get_job(db: Database, identifier: str) -> DatasheetJob:
    """Read one durable model job without exposing its approved outgoing payload."""
    with db.session() as session:
        row = session.get(DatasheetJobRow, identifier)
        if row is None:
            msg = "Datasheet model job not found"
            raise NotFoundError(msg)
        return _job_view(row)


def _require_fence(
    session: Session,
    identifier: str,
    fence: DatasheetFence,
) -> DatasheetJobRow:
    task = session.scalar(select(TaskRow).where(TaskRow.id == fence.task_id).with_for_update())
    shard = session.scalar(select(ShardRow).where(ShardRow.id == fence.shard_id).with_for_update())
    row = session.get(DatasheetJobRow, identifier, with_for_update=True)
    if (
        task is None
        or shard is None
        or row is None
        or task.datasheet_job_id != identifier
        or row.task_id != task.id
        or task.state not in {"QUEUED", "RUNNING"}
        or shard.task_id != task.id
        or shard.state != "RUNNING"
        or shard.lease_owner != fence.owner
        or row.status != "QUEUED"
    ):
        msg = "Datasheet model job no longer owns its active shard lease"
        raise ConflictError(msg)
    return row


def validate_fence(db: Database, identifier: str, fence: DatasheetFence) -> None:
    """Reject stale workers before reserving budget or sending frozen facts."""
    with db.session() as session:
        _require_fence(session, identifier, fence)


def job_input(
    db: Database,
    identifier: str,
    fence: DatasheetFence,
) -> tuple[DatasheetJob, DatasheetPrepared]:
    """Restore server-owned approved generation inputs for a leased worker."""
    with db.session() as session:
        row = _require_fence(session, identifier, fence)
        return _job_view(row), DatasheetPrepared.model_validate(row.prepared)


def schedule_job(
    session: Session, plan: ActionPlan, params: GenerateDatasheetParams
) -> OperationResult:
    """Schedule one empty-input shard whose only output is a checked document."""
    if params.prepared is None:
        msg = "Datasheet model task has no frozen facts"
        raise ConflictError(msg)
    identifier = plan.operation_id or plan.id
    task = TaskRow(
        id=new_id(),
        dataset_id=params.dataset_id,
        idempotency_key=f"action:{plan.id}",
        input_version_id=params.version_id,
        datasheet_job_id=identifier,
    )
    session.add(task)
    session.flush()
    job = DatasheetJob(
        id=identifier,
        task_id=task.id,
        dataset_id=params.dataset_id,
        version_id=params.version_id,
        language=params.language,
        provider=params.provider,
        created_at=plan.created_at,
    )
    session.add(
        DatasheetJobRow(
            id=identifier,
            task_id=task.id,
            payload=job.model_dump(mode="json"),
            prepared=params.prepared.model_dump(mode="json"),
        )
    )
    session.add(ShardRow(task_id=task.id, ordinal=0, inputs=[]))
    return OperationResult(
        task_id=task.id,
        outputs=[AssetRef(asset_type="datasheet_job", asset_id=identifier)],
        details={"job_id": identifier},
    )


def publish_completion(session: Session, completion: DatasheetCompletion, task_id: str) -> None:
    """Persist a validated model result only as part of owned shard completion."""
    row = session.get(DatasheetJobRow, completion.job_id, with_for_update=True)
    if row is None or row.task_id != task_id or row.status != "QUEUED":
        msg = "Datasheet completion does not own its queued job"
        raise ConflictError(msg)
    _validate_completion(row, completion)
    document = save_in_session(session, completion.document)
    row.status = "COMPLETED"
    row.payload = {**row.payload, "document_id": document.id}


def _validate_completion(row: DatasheetJobRow, completion: DatasheetCompletion) -> None:
    job = DatasheetJob.model_validate(row.payload)
    prepared = DatasheetPrepared.model_validate(row.prepared)
    document = completion.document
    checked = validate_sections(document.sections, prepared.facts, job.language)
    if (
        document.id != job.id
        or document.dataset_id != job.dataset_id
        or document.version_id != job.version_id
        or document.language != job.language
        or document.mode != "model"
        or document.facts != prepared.facts
        or document.published
        or document.stale
        or checked.dropped_sentences
        or checked.sections != document.sections
    ):
        msg = "Datasheet completion differs from its frozen checked generation inputs"
        raise ConflictError(msg)


def finish_failed(session: Session, identifier: str, error: str, *, cancelled: bool) -> None:
    """Keep failed or cancelled task outcomes visible without creating a document."""
    row = session.get(DatasheetJobRow, identifier, with_for_update=True)
    if row is not None and row.status == "QUEUED":
        row.status, row.error = "CANCELLED" if cancelled else "FAILED", error
