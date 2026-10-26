# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist frozen graph jobs and fenced block progress through typed interfaces."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.kg_cache import KGCacheKey
from datakeel.core.kg_execution import KGJob, KGLeaseFence, KGReport, KGRun
from datakeel.core.kg_models import ExtractionResult
from datakeel.core.models import new_id, utcnow
from datakeel.storage.action_selection import selected_files
from datakeel.storage.database import Database, ShardRow, TaskRow
from datakeel.storage.kg_progress import failed_report
from datakeel.storage.kg_rows import KGCacheRow, KGRunRow

MAX_RUNS = 1000


def schedule_extraction(
    session: Session, plan: ActionPlan, params: RunKGExtractionParams
) -> OperationResult:
    """Create the run and its single durable shard in the accepted action transaction."""
    if params.prepared is None:
        msg = "Graph extraction requires a prepared snapshot"
        raise ValidationError(msg)
    identifier = new_id()
    task = TaskRow(
        dataset_id=params.dataset_id,
        idempotency_key=f"action:{plan.id}",
        total_shards=1,
        queue="cpu",
        input_version_id=params.version_id,
        kg_run_id=identifier,
    )
    session.add(task)
    session.flush()
    session.add(
        ShardRow(
            task_id=task.id,
            ordinal=0,
            inputs=[item.model_dump(mode="json") for item in selected_files(session, plan)],
        )
    )
    profile = params.prepared.profile
    run = KGRun(
        id=identifier,
        dataset_id=params.dataset_id,
        version_id=params.version_id,
        schema_id=params.schema_id,
        profile_id=params.profile_id,
        model=profile.model,
        extractor=profile.extractor,
        status="queued",
        created_at=utcnow(),
        task_id=task.id,
        report=KGReport(
            documents=len(params.prepared.documents),
            blocks=params.prepared.estimate.blocks,
            transcription_cost_upper_usd=params.prepared.transcription_cost_upper_usd,
        ),
    )
    job = KGJob(
        run=run,
        prepared=params.prepared,
        budget_tokens=params.budget_tokens,
        max_cost_usd=params.max_cost_usd,
    )
    session.add(
        KGRunRow(
            id=identifier,
            dataset_id=params.dataset_id,
            version_id=params.version_id,
            task_id=task.id,
            created_at=run.created_at.timestamp(),
            payload=job.model_dump(mode="json"),
        )
    )
    return OperationResult(task_id=task.id, details={"extraction_id": identifier})


def get_job(db: Database, identifier: str) -> KGJob:
    """Read an exact execution snapshot without exposing its persistence row."""
    with db.session() as session:
        row = session.get(KGRunRow, identifier)
        if row is None:
            msg = "Graph extraction run not found"
            raise NotFoundError(msg)
        return KGJob.model_validate(row.payload)


def list_runs(
    db: Database, dataset_id: str | None = None, version_id: str | None = None, limit: int = 100
) -> tuple[KGRun, ...]:
    """List bounded run reports in newest-first order."""
    if not 1 <= limit <= MAX_RUNS:
        msg = "Graph run limit must be between 1 and 1000"
        raise ValidationError(msg)
    statement = select(KGRunRow).order_by(KGRunRow.created_at.desc(), KGRunRow.id).limit(limit)
    if dataset_id:
        statement = statement.where(KGRunRow.dataset_id == dataset_id)
    if version_id:
        statement = statement.where(KGRunRow.version_id == version_id)
    with db.session() as session:
        return tuple(KGJob.model_validate(row.payload).run for row in session.scalars(statement))


def owned(session: Session, fence: KGLeaseFence) -> bool:
    """Lock parent then shard using the queue's terminal-transition lock order."""
    task = session.scalar(select(TaskRow).where(TaskRow.id == fence.task_id).with_for_update())
    shard = session.scalar(select(ShardRow).where(ShardRow.id == fence.shard_id).with_for_update())
    return bool(
        task
        and task.state in {"QUEUED", "RUNNING"}
        and shard
        and shard.task_id == task.id
        and shard.state == "RUNNING"
        and shard.lease_owner == fence.owner
    )


def start_run(db: Database, identifier: str, fence: KGLeaseFence) -> bool:
    """Expose running state only while the exact worker attempt still owns its lease."""
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            return False
        row = session.get(KGRunRow, identifier)
        if row is None or row.task_id != fence.task_id:
            msg = "Graph run does not belong to the worker task"
            raise ValidationError(msg)
        job = KGJob.model_validate(row.payload)
        row.payload = job.model_copy(
            update={"run": job.run.model_copy(update={"status": "running"})}
        ).model_dump(mode="json")
        session.commit()
        return True


def cached_block(db: Database, key: KGCacheKey) -> ExtractionResult | None:
    """Read a successful raw extraction by its complete semantic digest."""
    with db.session() as session:
        row = session.get(KGCacheRow, key.digest())
        return ExtractionResult.model_validate(row.payload) if row else None


def cache_block(
    db: Database, fence: KGLeaseFence, key: KGCacheKey, result: ExtractionResult
) -> bool:
    """Publish complete cache content only while the current worker remains authorized."""
    if result.finish_reason in {"length", "max_tokens"}:
        msg = "Truncated graph output cannot enter the successful block cache"
        raise ValidationError(msg)
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            return False
        if not db.sqlite:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"kg-cache:{key.digest()}"},
            )
        if session.get(KGCacheRow, key.digest()) is None:
            session.add(
                KGCacheRow(
                    key=key.digest(),
                    key_payload=key.model_dump(mode="json"),
                    payload=result.model_dump(mode="json"),
                )
            )
        session.commit()
        return True


def save_progress(db: Database, fence: KGLeaseFence, report: KGReport) -> bool:
    """Checkpoint completed block counts under the same lease fence as cache publication."""
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            return False
        row = session.scalar(select(KGRunRow).where(KGRunRow.task_id == fence.task_id))
        if row is None:
            msg = "Graph progress does not belong to an extraction run"
            raise ValidationError(msg)
        job = KGJob.model_validate(row.payload)
        row.payload = job.model_copy(
            update={"run": job.run.model_copy(update={"report": report})}
        ).model_dump(mode="json")
        session.commit()
        return True


def finish_failed(session: Session, identifier: str, reason: str) -> None:
    """Keep terminal run reports visible when authorization or provider construction fails."""
    row = session.get(KGRunRow, identifier)
    if row is None:
        return
    job = KGJob.model_validate(row.payload)
    report = failed_report(session, job, reason)
    run = job.run.model_copy(
        update={"status": "failed", "completed_at": utcnow(), "report": report}
    )
    row.payload = job.model_copy(update={"run": run}).model_dump(mode="json")
