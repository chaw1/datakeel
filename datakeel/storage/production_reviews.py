# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Submission, human review and explicit rework without rewriting annotation history."""

from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import (
    ReopenTaskParams,
    ReviewTaskParams,
    SubmitTaskParams,
)
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import ProductionTask, Review
from datakeel.storage.production_assignments import active_assignment, finish_assignment
from datakeel.storage.production_revisions import require_holder
from datakeel.storage.production_rows import ProductionReviewRow
from datakeel.storage.production_tasks import (
    require_mutable_project,
    require_task,
    task_view,
    transition_task,
)


def submit_task(session: Session, params: SubmitTaskParams, actor: str) -> ProductionTask:
    """Approve personal work automatically, or submit the current group revision for review."""
    task = require_task(session, params.task_id)
    project = require_mutable_project(session, task.project_id)
    require_holder(session, task, actor)
    if task.state not in {"pending", "in_progress"} or task.latest_revision_id is None:
        message = "Submission requires an editable task with a saved revision"
        raise ConflictError(message)
    if task.annotator_id is None:
        task.annotator_id = actor
    if project.workflow_tier == "personal":
        task.approved_revision_id = task.latest_revision_id
        transition_task(session, task, "approved")
    else:
        transition_task(session, task, "submitted")
    return task_view(task)


def review_task(session: Session, params: ReviewTaskParams, actor: str) -> Review:
    """Record a decision against the submitted head and return rework to its original owner."""
    task = require_task(session, params.task_id)
    project = require_mutable_project(session, task.project_id)
    if project.workflow_tier == "personal":
        message = "Personal projects use automatic system approval without review records"
        raise ValidationError(message)
    if (
        task.state not in {"submitted", "in_review"}
        or task.latest_revision_id != params.revision_id
    ):
        message = "Review requires the current submitted revision"
        raise ConflictError(message)
    assignment = active_assignment(session, task.id, "review")
    if assignment is not None and assignment.actor != actor:
        message = "Task review is assigned to another reviewer"
        raise AuthorizationError(message)
    if params.decision == "rework" and not params.issues:
        message = "Rework requires at least one issue"
        raise ValidationError(message)
    review = Review(
        id=new_id(),
        task_id=task.id,
        revision_id=params.revision_id,
        decision=params.decision,
        issues=params.issues,
        actor=actor,
        round=task.round,
        created_at=utcnow(),
    )
    session.add(
        ProductionReviewRow(
            id=review.id,
            task_id=task.id,
            project_id=task.project_id,
            annotator_id=task.annotator_id or actor,
            decision=params.decision,
            payload=review.model_dump(mode="json"),
        )
    )
    finish_assignment(session, task.id, "review")
    if params.decision == "approve":
        task.approved_revision_id = task.latest_revision_id
        finish_assignment(session, task.id, "annotation")
        transition_task(session, task, "approved")
    else:
        task.round += 1
        task.approved_revision_id = None
        transition_task(session, task, "pending")
    return review


def reopen_task(session: Session, params: ReopenTaskParams) -> ProductionTask:
    """Reopen unfinalized work while retaining its prior revision, review and assignment history."""
    task = require_task(session, params.task_id)
    require_mutable_project(session, task.project_id)
    if task.state == "finalized":
        message = "Finalized tasks cannot be reopened"
        raise ConflictError(message)
    finish_assignment(session, task.id, "review")
    task.round += 1
    task.approved_revision_id = None
    transition_task(session, task, "pending")
    return task_view(task)
