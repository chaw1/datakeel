# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded reads behind one-sentence task selectors such as a holder's untouched tasks."""

from sqlalchemy import func, select

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelSet
from datakeel.storage.database import Database
from datakeel.storage.production_catalog_impact import migration_impact
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow

OPEN_STATES = ("pending", "in_progress")


class TaskSnapshot(BoundaryModel):
    """One task as a one-sentence selector sees it: list number, state and current holder."""

    id: str
    number: int
    state: str
    round: int
    package_id: str
    annotated: bool
    holder: str | None = None
    stage: str | None = None


def task_snapshots(db: Database, project_id: str, limit: int = 10000) -> list[TaskSnapshot]:
    """Every task of one project in the task list's order, with its active assignment."""
    bounded = min(max(limit, 1), 10000)
    with db.session() as session:
        rows = session.scalars(
            select(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project_id)
            .order_by(ProductionTaskRow.id)
            .limit(bounded)
        ).all()
        held = session.execute(
            select(
                ProductionAssignmentRow.task_id,
                ProductionAssignmentRow.actor,
                ProductionAssignmentRow.stage,
            )
            .join(ProductionTaskRow, ProductionAssignmentRow.task_id == ProductionTaskRow.id)
            .where(
                ProductionTaskRow.project_id == project_id,
                ProductionAssignmentRow.active.is_(True),
            )
        ).all()
    holders = {str(task): (str(actor), str(stage)) for task, actor, stage in held}
    return [
        TaskSnapshot(
            id=row.id,
            number=number,
            state=row.state,
            round=row.round,
            package_id=row.package_id,
            annotated=row.latest_revision_id is not None,
            holder=holders.get(row.id, (None, None))[0],
            stage=holders.get(row.id, (None, None))[1],
        )
        for number, row in enumerate(rows, start=1)
    ]


def task_holders(db: Database, task_ids: list[str]) -> dict[str, str]:
    """Who currently holds each of these tasks for annotation; unheld tasks are absent."""
    if not task_ids:
        return {}
    statement = select(ProductionAssignmentRow.task_id, ProductionAssignmentRow.actor).where(
        ProductionAssignmentRow.task_id.in_(task_ids[:10000]),
        ProductionAssignmentRow.active.is_(True),
        ProductionAssignmentRow.stage == "annotation",
    )
    with db.session() as session:
        return {str(task): str(actor) for task, actor in session.execute(statement).all()}


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


def latest_label_set(
    db: Database, label_set_id: str, version: int | None = None
) -> LabelSet | None:
    """The newest stored version of one label set (or the given one), published or not."""
    with db.session() as session:
        version = version or session.scalar(
            select(func.max(ProductionLabelSetRow.version)).where(
                ProductionLabelSetRow.label_set_id == label_set_id
            )
        )
        row = (
            session.scalar(
                select(ProductionLabelSetRow).where(
                    ProductionLabelSetRow.label_set_id == label_set_id,
                    ProductionLabelSetRow.version == version,
                )
            )
            if version is not None
            else None
        )
        return LabelSet.model_validate(row.payload) if row is not None else None


def label_change_impact(db: Database, before: LabelSet, after: LabelSet) -> tuple[int, int]:
    """Annotations and revisions a planned version would migrate, as label_set_diff counts."""
    with db.session() as session:
        return migration_impact(session, before, after)
