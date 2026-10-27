# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Idempotent task submissions and durable execution progress."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import new_id
from datakeel.pipeline import Pipeline
from datakeel.storage.dataset_service import task_artifacts
from datakeel.storage.task_models import TaskView
from datakeel.storage.task_queries import list_tasks, query_task
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.storage.views import FileView, View

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskInput(View):
    """Task target, replay identity, and pipeline execution settings."""

    dataset_id: str
    version_id: str | None = None
    idempotency_key: str = Field(default_factory=new_id)
    pipeline: Pipeline | None = None
    shards: int = Field(default=1, ge=1, le=128)
    queue: Literal["cpu", "io", "gpu"] = "cpu"


@router.post("", status_code=202)
def submit(body: TaskInput, db: DatabaseDependency) -> TaskView:
    """Submit a task idempotently against a validated immutable input snapshot."""
    identifier = DatabaseQueue(db).submit(
        body.dataset_id,
        body.idempotency_key,
        body.pipeline,
        shards=body.shards,
        queue=body.queue,
        version_id=body.version_id,
    )
    return query_task(db, identifier)


@router.get("")
def tasks(db: DatabaseDependency) -> list[TaskView]:
    """List durable task states and completion progress."""
    return list_tasks(db)


@router.get("/{identifier}")
def task(identifier: str, db: DatabaseDependency) -> TaskView:
    """Read one task with its shard states."""
    return query_task(db, identifier)


@router.get("/{identifier}/artifacts")
def artifacts(identifier: str, db: DatabaseDependency, request: Request) -> list[FileView]:
    """Read published artifacts for a completed task under the same query-scope guard."""
    return task_artifacts(
        db,
        identifier,
        access=AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
        ),
    )
