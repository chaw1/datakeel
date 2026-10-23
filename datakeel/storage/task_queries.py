# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read tasks without leaking database rows beyond the storage boundary."""

from sqlalchemy import select

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import Database, TaskRow
from datakeel.storage.task_models import TaskView
from datakeel.storage.task_queue import task_dict


def query_task(db: Database, task_id: str) -> TaskView:
    """Read one task with progress or raise a domain not-found error."""
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        if task is None:
            msg = "Task not found"
            raise NotFoundError(msg)
        return TaskView.model_validate(task_dict(db, task))


def list_tasks(db: Database) -> list[TaskView]:
    """List tasks in descending creation order."""
    with db.session() as session:
        tasks = session.scalars(select(TaskRow).order_by(TaskRow.created_at.desc()))
        return [TaskView.model_validate(task_dict(db, task)) for task in tasks]
