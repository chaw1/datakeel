# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose public task projections with optional domain reports."""

from datakeel.storage.database import Database
from datakeel.storage.vector_reports import vector_task_report
from datakeel.worker_store import task_queries
from datakeel.worker_store.task_models import TaskView


def _with_vector(db: Database, view: TaskView) -> TaskView:
    vector = vector_task_report(db, view.id)
    return view.model_copy(
        update={
            "vector": vector,
            "partial": view.partial
            or (
                view.state == "COMPLETED"
                and vector is not None
                and vector.status == "partial_success"
            ),
        }
    )


def query_task(db: Database, task_id: str) -> TaskView:
    """Read a task with its committed fake vector outcome when present."""
    return _with_vector(db, task_queries.query_task(db, task_id))


def list_tasks(db: Database) -> list[TaskView]:
    """Keep creation order and all optional reports for existing list consumers."""
    return [_with_vector(db, view) for view in task_queries.list_tasks(db)]
