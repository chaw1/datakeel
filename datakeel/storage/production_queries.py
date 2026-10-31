# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed production reads and target project resolution for server-side authorization."""

from collections.abc import Mapping

from pydantic import JsonValue
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.production_models import (
    TASK_STATES,
    AnnotationRevision,
    Assignment,
    ProductionProgress,
    ProductionTask,
    Project,
    Review,
    StateCount,
    TaskPackage,
)
from datakeel.storage.annotation_frames import revision_view
from datakeel.storage.database import Database
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionSummaryRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_project, task_view

REWORK_WARNING_ROUNDS = 3


def project_for_params(
    session: Session,
    params: BoundaryModel | Mapping[str, JsonValue],
) -> str | None:
    """Resolve indirect task and package targets and reject mixed-project batch authorization."""
    values: Mapping[str, JsonValue] = (
        JsonDocument.model_validate(params.model_dump(mode="json")).root
        if isinstance(params, BoundaryModel)
        else params
    )
    identifiers: set[str] = set()
    project_id = values.get("project_id")
    if isinstance(project_id, str):
        identifiers.add(require_project(session, project_id).id)
    for field, kind in (("task_id", ProductionTaskRow), ("package_id", ProductionPackageRow)):
        identifier = values.get(field)
        if isinstance(identifier, str):
            row = session.get(kind, identifier)
            if row is None:
                message = "Production target was not found"
                raise NotFoundError(message)
            identifiers.add(row.project_id)
    task_ids = values.get("task_ids")
    if isinstance(task_ids, list):
        for identifier in task_ids:
            if isinstance(identifier, str):
                row = session.get(ProductionTaskRow, identifier)
                if row is None:
                    message = "Production task was not found"
                    raise NotFoundError(message)
                identifiers.add(row.project_id)
    if len(identifiers) > 1:
        message = "A production action must target exactly one project"
        raise ValidationError(message)
    return next(iter(identifiers), None)


def get_project(db: Database, project_id: str) -> Project:
    """Read one immutable project configuration."""
    with db.session() as session:
        return require_project(session, project_id)


def list_projects(db: Database) -> tuple[Project, ...]:
    """List projects in stable identity order."""
    with db.session() as session:
        return tuple(
            Project.model_validate(row.payload)
            for row in session.scalars(
                select(ProductionProjectRow).order_by(ProductionProjectRow.id)
            )
        )


def list_packages(db: Database, project_id: str) -> tuple[TaskPackage, ...]:
    """Read partition metadata while leaving package state to bounded summary reads."""
    with db.session() as session:
        require_project(session, project_id)
        return tuple(
            TaskPackage.model_validate(row.payload)
            for row in session.scalars(
                select(ProductionPackageRow)
                .where(ProductionPackageRow.project_id == project_id)
                .order_by(ProductionPackageRow.id)
            )
        )


def list_tasks(db: Database, project_id: str, limit: int = 10000) -> tuple[ProductionTask, ...]:
    """Return a bounded stable task listing for generated data and command-line workflows."""
    with db.session() as session:
        require_project(session, project_id)
        return tuple(
            task_view(row)
            for row in session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.project_id == project_id)
                .order_by(ProductionTaskRow.id)
                .limit(min(max(limit, 1), 10000))
            )
        )


def get_task(db: Database, task_id: str) -> ProductionTask:
    """Read a task without taking a write lock."""
    with db.session() as session:
        row = session.get(ProductionTaskRow, task_id)
        if row is None:
            message = "Production task was not found"
            raise NotFoundError(message)
        return task_view(row)


def list_revisions(db: Database, task_id: str) -> tuple[AnnotationRevision, ...]:
    """Return the complete immutable revision history for one task."""
    with db.session() as session:
        return tuple(
            revision_view(session, row)
            for row in session.scalars(
                select(ProductionRevisionRow).where(ProductionRevisionRow.task_id == task_id)
            )
        )


def list_assignments(db: Database, task_id: str) -> tuple[Assignment, ...]:
    """Read effective and historical assignments without expiring leases in this phase."""
    with db.session() as session:
        return tuple(
            Assignment.model_validate(row.payload)
            for row in session.scalars(
                select(ProductionAssignmentRow).where(ProductionAssignmentRow.task_id == task_id)
            )
        )


def list_reviews(db: Database, task_id: str) -> tuple[Review, ...]:
    """Read exact-revision review evidence, with no synthetic personal reviews."""
    with db.session() as session:
        return tuple(
            Review.model_validate(row.payload)
            for row in session.scalars(
                select(ProductionReviewRow).where(ProductionReviewRow.task_id == task_id)
            )
        )


def project_progress(
    db: Database,
    project_id: str,
    package_id: str | None = None,
) -> ProductionProgress:
    """Read six maintained counters and an indexed list of tasks reworked at least three times."""
    with db.session() as session:
        require_project(session, project_id)
        scope_id = package_id or project_id
        if package_id:
            package = session.get(ProductionPackageRow, package_id)
            if package is None or package.project_id != project_id:
                message = "Package was not found within the selected project"
                raise NotFoundError(message)
        counts = {
            row.state: row.count
            for row in session.scalars(
                select(ProductionSummaryRow).where(ProductionSummaryRow.scope_id == scope_id)
            )
        }
        rework = select(ProductionTaskRow.id).where(
            ProductionTaskRow.project_id == project_id,
            ProductionTaskRow.round >= REWORK_WARNING_ROUNDS,
        )
        if package_id:
            rework = rework.where(ProductionTaskRow.package_id == package_id)
        total = sum(counts.values())
        return ProductionProgress(
            project_id=project_id,
            package_id=package_id,
            total=total,
            counts=tuple(
                StateCount(state=state, count=counts.get(state, 0)) for state in TASK_STATES
            ),
            status=_progress_status(counts, total),
            rework_task_ids=tuple(session.scalars(rework.order_by(ProductionTaskRow.id))),
        )


def _progress_status(counts: dict[str, int], total: int) -> str:
    if total and counts.get("finalized", 0) == total:
        return "finalized"
    if total and counts.get("approved", 0) + counts.get("finalized", 0) == total:
        return "approved"
    return "pending" if counts.get("pending", 0) == total else "in_progress"


def next_task(
    db: Database,
    project_id: str,
    actor: str = "local",
    package_id: str | None = None,
) -> ProductionTask | None:
    """Select the next personal or owned annotation task using indexed state and ordering."""
    with db.session() as session:
        project = require_project(session, project_id)
        query = select(ProductionTaskRow).where(
            ProductionTaskRow.project_id == project_id,
            ProductionTaskRow.state.in_(["pending", "in_progress"]),
        )
        if project.workflow_tier != "personal":
            query = query.where(
                or_(
                    ProductionTaskRow.annotator_id == actor,
                    (ProductionTaskRow.state == "pending") & (ProductionTaskRow.round == 0),
                )
            )
        if package_id is not None:
            query = query.where(ProductionTaskRow.package_id == package_id)
        if project.workflow_tier != "personal":
            query = query.order_by(
                case(
                    ((ProductionTaskRow.round > 0) & (ProductionTaskRow.annotator_id == actor), 0),
                    (ProductionTaskRow.annotator_id == actor, 1),
                    else_=2,
                )
            )
        row = session.scalar(
            query.order_by(ProductionTaskRow.priority.desc(), ProductionTaskRow.id).limit(1)
        )
        return task_view(row) if row else None
