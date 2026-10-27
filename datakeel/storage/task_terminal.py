# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish immutable task terminal times and events in the owning transaction."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.storage.database import OutboxRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.dq_results import finish_failed as finish_dq_failed
from datakeel.storage.kg_store import finish_failed


def complete_task(session: Session, task: TaskRow, error: str | None) -> None:
    """Finalize a failed task or the last completed shard while its parent is locked."""
    siblings = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task.id)))
    if error:
        task.state, task.error = "FAILED", error
        _cancel_shards(siblings)
    elif all(sibling.state == "COMPLETED" for sibling in siblings):
        task.state = "COMPLETED"
        manifest = [
            item
            for sibling in sorted(siblings, key=lambda item: item.ordinal)
            for item in sibling.outputs
        ]
        if task.kg_run_id is None and task.dq_run_id is None:
            session.add(VersionRow(dataset_id=task.dataset_id, task_id=task.id, manifest=manifest))
    if task.state in ("COMPLETED", "FAILED"):
        _publish_terminal(session, task)


def cancel_task(session: Session, task: TaskRow) -> None:
    """Cancel the locked task and its remaining shards in the same transaction."""
    siblings = list(
        session.scalars(select(ShardRow).where(ShardRow.task_id == task.id).with_for_update())
    )
    task.state = "CANCELLED"
    _cancel_shards(siblings)
    _publish_terminal(session, task)


def _cancel_shards(siblings: list[ShardRow]) -> None:
    for sibling in siblings:
        if sibling.state in ("QUEUED", "RUNNING"):
            sibling.state, sibling.lease_owner = "CANCELLED", None


def _publish_terminal(session: Session, task: TaskRow) -> None:
    if task.kg_run_id and task.state in {"FAILED", "CANCELLED"}:
        finish_failed(session, task.kg_run_id, task.error or "Graph task cancelled")
    if task.dq_run_id and task.state in {"FAILED", "CANCELLED"}:
        finish_dq_failed(
            session,
            task.dq_run_id,
            task.error or "Quality task cancelled",
            cancelled=task.state == "CANCELLED",
            started_at=datetime.fromtimestamp(task.created_at, UTC),
        )
    task.finished_at = utcnow().timestamp()
    terminal = LineageEvent(
        idempotency_key=f"task:{task.id}:terminal",
        event_type="TASK_TERMINAL",
        operator=(
            "dq.complete"
            if task.dq_run_id
            else "kg.complete"
            if task.kg_run_id
            else "pipeline.complete"
        ),
        run_state=task.state,
        source_module="worker",
        source_ref=task.id,
        inputs=[AssetRef(asset_id=task.dataset_id)],
        outputs=[AssetRef(asset_type="task", asset_id=task.id, display_name="Pipeline run")],
        quality={"shards": task.total_shards},
    )
    session.add(
        OutboxRow(
            idempotency_key=terminal.idempotency_key,
            payload=terminal.model_dump(mode="json"),
        )
    )
