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
from datakeel.core.production_models import ProductionTask, Project, Review
from datakeel.storage.production_assignments import active_assignment, finish_assignment
from datakeel.storage.production_leases import arm_lease, raise_if_reclaimed, require_live_lease
from datakeel.storage.production_revisions import require_holder
from datakeel.storage.production_rows import ProductionReviewRow, ProductionTaskRow
from datakeel.storage.production_separation import require_separation
from datakeel.storage.production_tasks import (
    require_mutable_project,
    require_task,
    task_view,
    transition_task,
)

# Reopening these states sends finished work back, which is one rework round.
REWORK_STATES = frozenset({"submitted", "in_review", "approved"})


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
    if assignment is None or assignment.actor != actor:
        raise_if_reclaimed(session, task.id, actor, "review")
    if assignment is not None and assignment.actor != actor:
        message = "Task review is assigned to another reviewer"
        raise AuthorizationError(message)
    if assignment is not None:
        require_live_lease(assignment, utcnow())
    require_separation(session, project, task, actor)
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
    finish_assignment(session, task.id, "review", "reviewed")
    if params.decision == "approve":
        task.approved_revision_id = task.latest_revision_id
        finish_assignment(session, task.id, "annotation", "approved")
        transition_task(session, task, "approved")
    else:
        return_for_rework(session, project, task)
    return review


def return_for_rework(session: Session, project: Project, task: ProductionTaskRow) -> None:
    """Count one rework round and give the retained annotation holder a fresh team lease."""
    task.round += 1
    task.approved_revision_id = None
    transition_task(session, task, "pending")
    holder = active_assignment(session, task.id, "annotation")
    if holder is not None and project.workflow_tier == "team":
        arm_lease(holder, project, utcnow())


def reopen_task(session: Session, params: ReopenTaskParams) -> ProductionTask:
    """Return submitted or approved work for rework; reopening editable work changes nothing.

    Only work that was submitted or approved and is sent back counts as a rework round, as in
    design section 5. A pending or in-progress task is already open, so its round, state,
    assignment and revisions stay as they are; the action audit still records the request.
    """
    task = require_task(session, params.task_id)
    project = require_mutable_project(session, task.project_id)
    if task.state == "finalized":
        message = "Finalized tasks cannot be reopened"
        raise ConflictError(message)
    if task.state in REWORK_STATES:
        finish_assignment(session, task.id, "review", "reopened")
        return_for_rework(session, project, task)
    return task_view(task)
