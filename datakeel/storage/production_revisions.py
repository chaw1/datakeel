# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only annotation saving guarded by ownership and an optimistic previous pointer."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import AnnotationRevision
from datakeel.storage.production_catalog import normalize_annotation, validate_annotation
from datakeel.storage.production_leases import raise_if_reclaimed, require_live_lease
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_mutable_project, transition_task


class RevisionConflictError(ConflictError):
    """Return the authoritative current revision with a failed optimistic save."""

    def __init__(self, latest_revision: AnnotationRevision | None) -> None:
        """Expose the server head for typed API conflict responses and action errors."""
        self.latest_revision = latest_revision
        super().__init__(
            "Annotation revision conflict; latest_revision="
            + (latest_revision.model_dump_json() if latest_revision else "null")
        )


def require_holder(session: Session, task: ProductionTaskRow, actor: str) -> None:
    """Allow personal work directly and require an effective annotation owner in group projects."""
    project = require_mutable_project(session, task.project_id)
    if project.workflow_tier == "personal":
        return
    assignment = session.scalar(
        select(ProductionAssignmentRow).where(
            ProductionAssignmentRow.task_id == task.id,
            ProductionAssignmentRow.stage == "annotation",
            ProductionAssignmentRow.active.is_(True),
        )
    )
    if assignment is None or assignment.actor != actor:
        raise_if_reclaimed(session, task.id, actor, "annotation")
        message = "Only the current annotation assignment holder may modify this task"
        raise AuthorizationError(message)
    require_live_lease(assignment, utcnow())


def current_revision(session: Session, task: ProductionTaskRow) -> AnnotationRevision | None:
    """Read the task's current immutable revision, if it has ever been saved."""
    row = (
        session.get(ProductionRevisionRow, task.latest_revision_id)
        if task.latest_revision_id
        else None
    )
    return AnnotationRevision.model_validate(row.payload) if row else None


def append_revision(
    session: Session,
    task: ProductionTaskRow,
    params: SaveRevisionParams,
    actor: str,
) -> AnnotationRevision:
    """Append a revision through compare-and-swap; model imports use the same immutable path."""
    project = require_mutable_project(session, task.project_id)
    params = params.model_copy(
        update={
            "annotation": normalize_annotation(session, project, params.annotation),
        }
    )
    if params.source == "human":
        require_holder(session, task, actor)
    if task.state not in {"pending", "in_progress"}:
        message = "Only pending or in-progress tasks accept annotation revisions"
        raise ConflictError(message)
    _validate_revision(session, task, params)
    revision = AnnotationRevision(
        id=new_id(),
        task_id=task.id,
        actor=actor,
        created_at=utcnow(),
        **params.model_dump(exclude={"request_id", "task_id"}),
    )
    changed = session.scalar(
        update(ProductionTaskRow)
        .where(
            ProductionTaskRow.id == task.id,
            ProductionTaskRow.latest_revision_id == params.previous_revision_id,
        )
        .values(latest_revision_id=revision.id, confidence=revision.confidence)
        .returning(ProductionTaskRow.id)
    )
    if changed is None:
        session.refresh(task)
        raise RevisionConflictError(current_revision(session, task))
    session.add(
        ProductionRevisionRow(
            id=revision.id,
            task_id=task.id,
            project_id=task.project_id,
            source=revision.source,
            actor=actor,
            confidence=revision.confidence,
            payload=revision.model_dump(mode="json"),
        )
    )
    if params.source == "human":
        task.annotator_id = actor
        transition_task(session, task, "in_progress")
    return revision


def _validate_revision(
    session: Session, task: ProductionTaskRow, params: SaveRevisionParams
) -> None:
    if params.annotation.sample_id != task.sample_id:
        message = "Revision annotation sample_id does not match the production task"
        raise ValidationError(message)
    if params.source == "model" and (not params.model_name or not params.model_version):
        message = "Model revisions require model_name and model_version"
        raise ValidationError(message)
    project = require_mutable_project(session, task.project_id)
    validate_annotation(session, project, params.annotation)
