# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialize a stored task with its shard progress and per-file media failures."""

from typing import Any

from sqlalchemy import select

from datakeel.core.media_metadata import media_failure
from datakeel.storage.database import Database, ShardRow, TaskRow


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
    failures = [
        failure.model_dump(mode="json")
        for shard in shards
        for item in shard.outputs or []
        if (
            failure := media_failure(
                str(item.get("id", "")), str(item.get("filename", "")), item.get("metadata") or {}
            )
        )
        is not None
    ]
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
        "failed_files": failures,
        "partial": state == "COMPLETED" and bool(failures),
    }
