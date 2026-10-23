# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable shard leases, fenced completion, and a transactional outbox."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.evidence_execution import PendingExtraction
from datakeel.core.models import FileItem, LineageEvent, new_id, utcnow
from datakeel.pipeline import Pipeline, validate_pipeline
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.database import Database, DatasetRow, OutboxRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_store import record_extraction_in_session
from datakeel.storage.task_terminal import cancel_task, complete_task

MAX_SHARDS = 128


class Lease(BaseModel):
    """Frozen attempt identity and input manifest for one leased shard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shard_id: str
    task_id: str
    dataset_id: str
    owner: str
    inputs: list[FileItem]
    pipeline: Pipeline | None
    input_version_id: str | None = None


class TaskSource(Protocol):
    """Minimum durable queue interface for workers."""

    def claim(self, queue: str = "cpu") -> Lease | None:
        """Claim a queued shard with a unique fencing token."""
        ...

    def heartbeat(self, lease: Lease) -> bool:
        """Refresh an owned lease, returning false for a stale owner."""
        ...


class DatabaseQueue:
    """Coordinate idempotent task submission and fenced terminal transitions."""

    def __init__(self, db: Database, lease_seconds: float = 30, max_attempts: int = 3) -> None:
        """Bind the queue to its storage and retry policy."""
        self.db = db
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    def submit(
        self,
        dataset_id: str,
        key: str,
        pipeline: Pipeline | dict[str, Any] | None = None,
        *,
        shards: int = 1,
        queue: str = "cpu",
        version_id: str | None = None,
    ) -> str:
        """Persist a frozen input manifest, or return its idempotent task."""
        pipeline = _submission_pipeline(pipeline, shards)
        if shards < 1 or shards > MAX_SHARDS or queue not in ("cpu", "io", "gpu"):
            msg = "Invalid shard count or queue"
            raise ValidationError(msg)
        with self.db.session() as session:
            self.db.lock_writes(session)
            dataset = session.scalar(
                select(DatasetRow).where(DatasetRow.id == dataset_id).with_for_update()
            )
            if not dataset:
                msg = "Dataset not found"
                raise NotFoundError(msg)
            existing = session.scalar(select(TaskRow).where(TaskRow.idempotency_key == key))
            if existing:
                if (
                    existing.dataset_id != dataset_id
                    or _canonical_pipeline(existing.pipeline) != pipeline
                    or existing.queue != queue
                    or existing.total_shards != shards
                    or existing.input_version_id != version_id
                ):
                    msg = "Idempotency key already used with different parameters"
                    raise ConflictError(msg)
                return existing.id
            source_files = dataset.files
            if version_id:
                version = session.get(VersionRow, version_id)
                if not version or version.dataset_id != dataset_id:
                    msg = "Input version not found in dataset"
                    raise NotFoundError(msg)
                source_files = version.manifest
            task = TaskRow(
                dataset_id=dataset_id,
                idempotency_key=key,
                pipeline=pipeline,
                total_shards=shards,
                queue=queue,
                input_version_id=version_id,
            )
            session.add(task)
            session.flush()
            for index in range(shards):
                session.add(
                    ShardRow(task_id=task.id, ordinal=index, inputs=source_files[index::shards])
                )
            session.commit()
            return task.id

    def claim(self, queue: str = "cpu") -> Lease | None:
        """Lock and claim one shard using a new fencing token."""
        with self.db.session() as session:
            self.db.lock_writes(session)
            shard = session.scalar(
                select(ShardRow)
                .join(TaskRow)
                .where(
                    ShardRow.state == "QUEUED",
                    TaskRow.queue == queue,
                    TaskRow.state.in_(["QUEUED", "RUNNING"]),
                )
                .order_by(TaskRow.created_at, ShardRow.ordinal)
                .limit(1)
                .with_for_update(skip_locked=True, of=ShardRow)
            )
            if not shard:
                return None
            task = session.get(TaskRow, shard.task_id)
            if task is None:
                msg = "Task not found"
                raise NotFoundError(msg)
            owner = new_id()
            shard.state, shard.lease_owner, shard.heartbeat_at = (
                "RUNNING",
                owner,
                utcnow().timestamp(),
            )
            shard.attempts += 1
            lease = Lease(
                shard_id=shard.id,
                task_id=task.id,
                dataset_id=task.dataset_id,
                owner=owner,
                inputs=[FileItem.model_validate(value) for value in shard.inputs],
                pipeline=Pipeline.model_validate(task.pipeline)
                if task.pipeline is not None
                else None,
                input_version_id=_source_version(session, task),
            )
            session.commit()
            return lease

    def heartbeat(self, lease: Lease) -> bool:
        """Refresh an owned lease without reviving a stale attempt."""
        with self.db.session() as session:
            self.db.lock_writes(session)
            shard = session.scalar(
                select(ShardRow).where(ShardRow.id == lease.shard_id).with_for_update()
            )
            if not shard or shard.state != "RUNNING" or shard.lease_owner != lease.owner:
                return False
            shard.heartbeat_at = utcnow().timestamp()
            session.commit()
            return True

    def finish(
        self,
        lease: Lease,
        outputs: list[FileItem],
        events: list[LineageEvent],
        error: str | None = None,
        expired_before: float | None = None,
        *,
        evidence: tuple[PendingExtraction, ...] = (),
    ) -> bool:
        """Publish outputs and the terminal outbox atomically if the lease is owned."""
        with self.db.session() as session:
            self.db.lock_writes(session)
            # All terminal transitions serialize on the parent, then its shard.
            task = session.scalar(
                select(TaskRow).where(TaskRow.id == lease.task_id).with_for_update()
            )
            shard = session.scalar(
                select(ShardRow).where(ShardRow.id == lease.shard_id).with_for_update()
            )
            if not shard or shard.state != "RUNNING" or shard.lease_owner != lease.owner:
                return False
            if expired_before is not None and (shard.heartbeat_at or 0) >= expired_before:
                return False
            if task is None:
                msg = "Task not found"
                raise NotFoundError(msg)
            shard.state = "FAILED" if error else "COMPLETED"
            shard.outputs = [item.model_dump(mode="json") for item in outputs]
            shard.lease_owner = None
            for event in events:
                append_event(session, event)
            for pending in evidence:
                record_extraction_in_session(session, pending.event, pending.bundle)
            session.flush()
            complete_task(session, task, error)
            session.commit()
            return True

    def cancel(self, task_id: str) -> bool:
        """Cancel pending work once, fencing all leases and preserving terminal timestamps."""
        with self.db.session() as session:
            self.db.lock_writes(session)
            task = session.scalar(select(TaskRow).where(TaskRow.id == task_id).with_for_update())
            if task is None:
                msg = "Task not found"
                raise NotFoundError(msg)
            if task.state in ("COMPLETED", "FAILED", "CANCELLED"):
                return False
            cancel_task(session, task)
            session.commit()
            return True

    def reap(self) -> int:
        """Requeue expired attempts or persist terminal failure after exhaustion."""
        expired: list[Lease] = []
        requeued = 0
        cutoff = utcnow().timestamp() - self.lease_seconds
        with self.db.session() as session:
            self.db.lock_writes(session)
            shards = list(
                session.scalars(
                    select(ShardRow)
                    .where(
                        ShardRow.state == "RUNNING",
                        ShardRow.heartbeat_at < cutoff,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for shard in shards:
                if shard.attempts >= self.max_attempts:
                    task = session.get(TaskRow, shard.task_id)
                    if task is None:
                        msg = "Task not found"
                        raise NotFoundError(msg)
                    expired.append(
                        Lease(
                            shard_id=shard.id,
                            task_id=task.id,
                            dataset_id=task.dataset_id,
                            owner=shard.lease_owner or "",
                            inputs=[],
                            pipeline=None,
                        )
                    )
                else:
                    shard.state, shard.lease_owner = "QUEUED", None
                    requeued += 1
            session.commit()
        for lease in expired:
            requeued += self.finish(
                lease,
                [],
                [],
                error="Worker lease expired after maximum retries",
                expired_before=cutoff,
            )
        return requeued

    def relay(self) -> int:
        """Deliver append-only terminal events exactly once through idempotency."""
        with self.db.session() as session:
            self.db.lock_writes(session)
            rows = list(
                session.scalars(
                    select(OutboxRow)
                    .where(OutboxRow.delivered.is_(False))
                    .with_for_update(skip_locked=True)
                )
            )
            for row in rows:
                append_event(session, LineageEvent.model_validate(row.payload))
                row.delivered = True
            session.commit()
            return len(rows)


def task_dict(db: Database, task: TaskRow) -> dict[str, Any]:
    """Serialize a stored task with its current shard progress."""
    with db.session() as session:
        shards = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task.id)))
    completed = sum(shard.state == "COMPLETED" for shard in shards)
    state = (
        "RUNNING"
        if task.state == "QUEUED" and any(s.state == "RUNNING" for s in shards)
        else task.state
    )
    return {
        "id": task.id,
        "dataset_id": task.dataset_id,
        "input_version_id": task.input_version_id,
        "state": state,
        "progress": round(completed / task.total_shards * 100, 1),
        "total_shards": task.total_shards,
        "completed_shards": completed,
        "error": task.error,
        "created_at": task.created_at,
        "finished_at": task.finished_at,
        "shards": [
            {"id": s.id, "state": s.state, "attempts": s.attempts, "ordinal": s.ordinal}
            for s in shards
        ],
    }


def _canonical_pipeline(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return Pipeline.model_validate(value).model_dump(mode="json") if value is not None else None


def _submission_pipeline(
    value: Pipeline | dict[str, Any] | None, shards: int
) -> dict[str, Any] | None:
    if value is None:
        return None
    validate_pipeline(value)
    definition = Pipeline.model_validate(value)
    validate_shards(definition, shards)
    return definition.model_dump(mode="json")


def _source_version(session: Session, task: TaskRow) -> str:
    if task.input_version_id is not None:
        return task.input_version_id
    version = session.scalar(
        select(VersionRow)
        .where(VersionRow.dataset_id == task.dataset_id)
        .order_by(VersionRow.created_at, VersionRow.id)
    )
    if version is None:
        msg = "Task source manifest version is missing"
        raise NotFoundError(msg)
    return version.id
