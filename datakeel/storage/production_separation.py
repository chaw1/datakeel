# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier separation of duties: anyone who annotated a task, in any round, never reviews it."""

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from datakeel.core.errors import AuthorizationError
from datakeel.core.production_models import Project
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)


def annotators(session: Session, task: ProductionTaskRow) -> frozenset[str]:
    """Collect the current annotator, every human revision author and every annotation holder."""
    authors = session.scalars(
        select(ProductionRevisionRow.actor).where(
            ProductionRevisionRow.task_id == task.id, ProductionRevisionRow.source == "human"
        )
    )
    holders = session.scalars(
        select(ProductionAssignmentRow.actor).where(
            ProductionAssignmentRow.task_id == task.id,
            ProductionAssignmentRow.stage == "annotation",
        )
    )
    current = {task.annotator_id} if task.annotator_id else set[str]()
    return frozenset({*authors, *holders, *current})


def require_separation(
    session: Session, project: Project, task: ProductionTaskRow, actor: str
) -> None:
    """Reject review by an annotator of the task; only the team tier enforces this."""
    if project.workflow_tier == "team" and actor in annotators(session, task):
        message = (
            "Separation of duties: a person who annotated this task in any round cannot review it"
        )
        raise AuthorizationError(message)


def exclude_own_work(query: Select[ProductionTaskRow], actor: str) -> Select[ProductionTaskRow]:
    """Restrict a review queue to tasks the actor never annotated, using indexed subqueries."""
    authored = (
        select(ProductionRevisionRow.id)
        .where(
            ProductionRevisionRow.task_id == ProductionTaskRow.id,
            ProductionRevisionRow.actor == actor,
            ProductionRevisionRow.source == "human",
        )
        .exists()
    )
    held = (
        select(ProductionAssignmentRow.id)
        .where(
            ProductionAssignmentRow.task_id == ProductionTaskRow.id,
            ProductionAssignmentRow.actor == actor,
            ProductionAssignmentRow.stage == "annotation",
        )
        .exists()
    )
    return query.where(
        ~authored,
        ~held,
        (ProductionTaskRow.annotator_id.is_(None)) | (ProductionTaskRow.annotator_id != actor),
    )
