# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded reads behind one-sentence task selectors such as a holder's untouched tasks."""

from sqlalchemy import select

from datakeel.storage.database import Database
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow

OPEN_STATES = ("pending", "in_progress")


def held_tasks(
    db: Database,
    actor: str,
    *,
    project_id: str | None = None,
    untouched: bool = False,
    limit: int = 10000,
) -> list[tuple[str, str]]:
    """Return (project id, task id) for open annotation tasks the actor currently holds.

    Untouched tasks have no saved revision yet.
    """
    statement = (
        select(ProductionTaskRow.project_id, ProductionTaskRow.id)
        .join(ProductionAssignmentRow, ProductionAssignmentRow.task_id == ProductionTaskRow.id)
        .where(
            ProductionAssignmentRow.actor == actor,
            ProductionAssignmentRow.active.is_(True),
            ProductionAssignmentRow.stage == "annotation",
            ProductionTaskRow.state.in_(OPEN_STATES),
        )
        .order_by(ProductionTaskRow.project_id, ProductionTaskRow.id)
        .limit(min(max(limit, 1), 10000))
    )
    if project_id is not None:
        statement = statement.where(ProductionTaskRow.project_id == project_id)
    if untouched:
        statement = statement.where(ProductionTaskRow.latest_revision_id.is_(None))
    with db.session() as session:
        return [(str(project), str(task)) for project, task in session.execute(statement).all()]
