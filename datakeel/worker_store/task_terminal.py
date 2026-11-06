# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish immutable task terminal times and events in the owning transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.dataset_store.rows import VersionRow
from datakeel.worker_store.completion import CompletionRequest, CompletionResult, TaskCompletionPort
from datakeel.worker_store.rows import OutboxRow, ShardRow, TaskRow


def complete_task(
    session: Session,
    task: TaskRow,
    request: CompletionRequest,
    port: TaskCompletionPort,
    result: CompletionResult,
) -> None:
    """Finalize a failed task or the last completed shard while its parent is locked."""
    error = request.error
    if error:
        siblings = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task.id)))
        task.state, task.error = "FAILED", error
        _cancel_shards(siblings)
    elif (
        session.scalar(
            select(ShardRow.id)
            .where(ShardRow.task_id == task.id, ShardRow.state != "COMPLETED")
            .limit(1)
        )
        is None
    ):
        task.state = "COMPLETED"
        manifest = [
            item
            for outputs in session.scalars(
                select(ShardRow.outputs)
                .where(ShardRow.task_id == task.id)
                .order_by(ShardRow.ordinal)
            )
            for item in outputs
        ]
        if result.publish_version:
            session.add(VersionRow(dataset_id=task.dataset_id, task_id=task.id, manifest=manifest))
    if task.state in ("COMPLETED", "FAILED"):
        _publish_terminal(
            session, task, port.complete(request.model_copy(update={"phase": task.state}))
        )


def cancel_task(
    session: Session, task: TaskRow, request: CompletionRequest, port: TaskCompletionPort
) -> None:
    """Cancel the locked task and its remaining shards in the same transaction."""
    siblings = list(
        session.scalars(select(ShardRow).where(ShardRow.task_id == task.id).with_for_update())
    )
    task.state = "CANCELLED"
    _cancel_shards(siblings)
    _publish_terminal(
        session,
        task,
        port.complete(request.model_copy(update={"phase": "CANCELLED", "error": task.error})),
    )


def _cancel_shards(siblings: list[ShardRow]) -> None:
    for sibling in siblings:
        if sibling.state in ("QUEUED", "RUNNING"):
            sibling.state, sibling.lease_owner = "CANCELLED", None


def _publish_terminal(session: Session, task: TaskRow, result: CompletionResult) -> None:
    task.finished_at = utcnow().timestamp()
    terminal = LineageEvent(
        idempotency_key=f"task:{task.id}:terminal",
        event_type="TASK_TERMINAL",
        operator=result.operator,
        run_state=task.state,
        source_module="worker",
        source_ref=task.id,
        inputs=[AssetRef(asset_id=task.dataset_id)],
        outputs=[
            AssetRef(
                asset_type="task",
                asset_id=task.id,
                display_name=result.display_name,
            )
        ],
        quality={"shards": task.total_shards},
    )
    session.add(
        OutboxRow(
            idempotency_key=terminal.idempotency_key,
            payload=terminal.model_dump(mode="json"),
        )
    )
