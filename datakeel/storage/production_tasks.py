# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared production task locks, immutable projections and incremental state maintenance."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.production_models import TASK_STATES, ProductionTask, Project, TaskState
from datakeel.storage.production_counters import defer_counter_change
from datakeel.storage.production_rows import (
    ProductionProjectRow,
    ProductionSummaryRow,
    ProductionTaskRow,
)


def require_project(session: Session, project_id: str) -> Project:
    """Read project configuration through its frozen boundary model."""
    row = session.get(ProductionProjectRow, project_id, populate_existing=True)
    if row is None:
        message = "Production project was not found"
        raise NotFoundError(message)
    return Project.model_validate(row.payload)


def require_task(session: Session, task_id: str) -> ProductionTaskRow:
    """Lock one task before mutating any revision pointer or assignment."""
    row = session.scalar(
        select(ProductionTaskRow)
        .where(ProductionTaskRow.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        message = "Production task was not found"
        raise NotFoundError(message)
    return row


def task_view(row: ProductionTaskRow) -> ProductionTask:
    """Keep ORM rows inside storage by returning a frozen public task snapshot."""
    return ProductionTask(
        id=row.id,
        project_id=row.project_id,
        package_id=row.package_id,
        sample_id=row.sample_id,
        state=cast("TaskState", row.state),
        round=row.round,
        priority=row.priority,
        latest_revision_id=row.latest_revision_id,
        approved_revision_id=row.approved_revision_id,
        annotator_id=row.annotator_id,
        confidence=row.confidence,
    )


def require_mutable_project(session: Session, project_id: str) -> Project:
    """Reject task writes after a project has produced its final dataset version."""
    project = require_project(session, project_id)
    if project.finalized_version_id is not None:
        message = "Finalized projects cannot be changed; create a new project"
        raise ConflictError(message)
    return project


def initialize_summary(session: Session, scope_id: str, total: int = 0) -> None:
    """Create all six counters so later transitions need only bounded SQL updates."""
    session.add_all(
        ProductionSummaryRow(
            scope_id=scope_id, state=state, count=total if state == "pending" else 0
        )
        for state in TASK_STATES
    )


def transition_task(session: Session, task: ProductionTaskRow, state: TaskState) -> None:
    """Move task state; package and project counters change when the same transaction commits."""
    if task.state == state:
        return
    defer_counter_change(session, (task.project_id, task.package_id), task.state, state)
    task.state = state
