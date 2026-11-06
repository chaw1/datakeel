# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialize a stored task with its shard progress and per-file media failures."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.media_metadata import media_failure
from datakeel.worker_store.rows import ShardRow, TaskRow
from datakeel.worker_store.task_models import ShardView, TaskView


def task_view(session: Session, task: TaskRow) -> TaskView:
    """Serialize a stored task with its current shard progress."""
    shards = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task.id)))
    completed = sum(shard.state == "COMPLETED" for shard in shards)
    state = (
        "RUNNING"
        if task.state == "QUEUED" and any(s.state == "RUNNING" for s in shards)
        else task.state
    )
    failures = [
        failure
        for shard in shards
        for item in shard.outputs or []
        if (
            failure := media_failure(
                str(item.get("id", "")), str(item.get("filename", "")), item.get("metadata") or {}
            )
        )
        is not None
    ]
    return TaskView(
        id=task.id,
        dataset_id=task.dataset_id,
        input_version_id=task.input_version_id,
        state=state,
        progress=round(completed / task.total_shards * 100, 1),
        total_shards=task.total_shards,
        completed_shards=completed,
        error=task.error,
        created_at=task.created_at,
        finished_at=task.finished_at,
        shards=[
            ShardView(id=s.id, state=s.state, attempts=s.attempts, ordinal=s.ordinal)
            for s in shards
        ],
        failed_files=failures,
        partial=state == "COMPLETED" and bool(failures),
    )
