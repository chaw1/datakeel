# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded reads behind one-sentence task selectors such as a holder's untouched tasks."""

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError
from sqlalchemy import func, select

from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.core.errors import DatakeelError
from datakeel.core.models import BoundaryModel
from datakeel.core.prelabel_models import PrelabelEstimate
from datakeel.core.production_catalog_models import LabelSet
from datakeel.core.production_models import AssignmentStage, Project
from datakeel.storage.database import Database
from datakeel.storage.display_order import ordered_task_rows
from datakeel.storage.production_catalog_impact import migration_impact
from datakeel.storage.production_catalog_plans import catalog_requires_approval, prelabel_estimate
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_dispatch_rules import active_loads
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow
from datakeel.storage.production_separation import annotators
from datakeel.storage.production_template_versions import (
    latest_label_set_version,
    latest_template,
    locked_template,
)

OPEN_STATES = ("pending", "in_progress")
REVIEW_STATES = ("submitted", "in_review")


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
    annotator: str | None = None


def task_snapshots(db: Database, project_id: str, limit: int = 10000) -> list[TaskSnapshot]:
    """Every task of one project in the task list's order, with its active assignment."""
    bounded = min(max(limit, 1), 10000)
    with db.session() as session:
        rows = ordered_task_rows(
            session,
            project_id,
            session.scalars(
                select(ProductionTaskRow).where(ProductionTaskRow.project_id == project_id)
            ),
        )[:bounded]
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
            annotator=row.annotator_id,
        )
        for number, row in enumerate(rows, start=1)
    ]


def task_holders(db: Database, task_ids: list[str], stage: str = "annotation") -> dict[str, str]:
    """Who currently holds each of these tasks in this stage; unheld tasks are absent."""
    if not task_ids:
        return {}
    statement = select(ProductionAssignmentRow.task_id, ProductionAssignmentRow.actor).where(
        ProductionAssignmentRow.task_id.in_(task_ids[:10000]),
        ProductionAssignmentRow.active.is_(True),
        ProductionAssignmentRow.stage == stage,
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
    stage: str = "annotation",
) -> list[tuple[str, str]]:
    """Return (project id, task id) for open tasks the actor currently holds in one stage.

    Untouched tasks have no saved revision yet. In review, open means waiting for review.
    """
    statement = (
        select(ProductionTaskRow.project_id, ProductionTaskRow.id)
        .join(ProductionAssignmentRow, ProductionAssignmentRow.task_id == ProductionTaskRow.id)
        .where(
            ProductionAssignmentRow.actor == actor,
            ProductionAssignmentRow.active.is_(True),
            ProductionAssignmentRow.stage == stage,
            ProductionTaskRow.state.in_(OPEN_STATES if stage == "annotation" else REVIEW_STATES),
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


def newest_published_version(db: Database, label_set_id: str) -> int | None:
    """The newest published version of one label set, the one a new project would use."""
    with db.session() as session:
        versions = [
            LabelSet.model_validate(row.payload)
            for row in session.scalars(
                select(ProductionLabelSetRow).where(
                    ProductionLabelSetRow.label_set_id == label_set_id
                )
            )
        ]
    published = [item.version for item in versions if item.published]
    return max(published) if published else None


def held_projects(db: Database, actor: str) -> list[str]:
    """Projects in which the actor holds an open task now, at any stage."""
    statement = (
        select(ProductionTaskRow.project_id)
        .join(ProductionAssignmentRow, ProductionAssignmentRow.task_id == ProductionTaskRow.id)
        .where(ProductionAssignmentRow.actor == actor, ProductionAssignmentRow.active.is_(True))
        .distinct()
    )
    with db.session() as session:
        return sorted(str(project) for project in session.scalars(statement))


def open_load(db: Database, project_id: str, stage: AssignmentStage, person: str) -> int:
    """Open tasks a person holds in one stage, counted as the per-person limit counts them."""
    with db.session() as session:
        return active_loads(session, project_id, stage, (person,)).get(person, 0)


def own_work(db: Database, task_ids: list[str], person: str) -> list[str]:
    """Tasks among these the person annotated in any round, as review separation reads them."""
    with db.session() as session:
        return [
            task
            for task in task_ids
            if (row := session.get(ProductionTaskRow, task)) is not None
            and person in annotators(session, row)
        ]


def newer_versions(db: Database, project: Project) -> bool:
    """Whether a newer template revision or published label-set version exists to move to."""
    with db.session() as session:
        locked = locked_template(session, project)
        template = project.template_id
        newer = (
            locked is not None
            and template is not None
            and latest_template(session, template).revision > locked.revision
        )
        labels = latest_label_set_version(session, project.label_set_id)
        return newer or (labels or 0) > project.label_set_version


def cloud_prelabel(
    db: Database, params: dict[str, JsonValue]
) -> tuple[PrelabelEstimate, bool] | None:
    """A cloud pre-label run's estimate and whether it is over budget, as preparation prices it.

    None for an offline model or a step whose project or model is not settled yet.
    """
    try:
        checked = RunPrelabelParams.model_validate({**params, "request_id": "plan"})
        with db.session() as session:
            estimate = prelabel_estimate(session, checked)
            if estimate is None:
                return None
            return estimate, catalog_requires_approval(session, checked)
    except (ModelValidationError, DatakeelError):
        return None
