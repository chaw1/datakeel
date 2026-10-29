# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exclusive human assignment and lock-safe task claiming for group production."""

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ClaimTaskParams,
    ReleaseTaskParams,
)
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.identity_models import User
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import (
    Assignment,
    AssignmentSource,
    AssignmentStage,
    ProductionTask,
)
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.production_dispatch_rules import require_capacity, require_claim_strategy
from datakeel.storage.production_leases import end_assignment
from datakeel.storage.production_members import record_project_member
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionTaskRow,
)
from datakeel.storage.production_separation import exclude_own_work, require_separation
from datakeel.storage.production_tasks import (
    require_mutable_project,
    require_task,
    task_view,
    transition_task,
)


def active_assignment(
    session: Session,
    task_id: str,
    stage: AssignmentStage,
) -> ProductionAssignmentRow | None:
    """Read the single effective assignment protected by the database partial unique index."""
    return session.scalar(
        select(ProductionAssignmentRow).where(
            ProductionAssignmentRow.task_id == task_id,
            ProductionAssignmentRow.stage == stage,
            ProductionAssignmentRow.active.is_(True),
        )
    )


def finish_assignment(
    session: Session, task_id: str, stage: AssignmentStage, reason: str = "finished"
) -> None:
    """Retire an assignment without deleting its actor and lease history."""
    row = active_assignment(session, task_id, stage)
    if row is not None:
        end_assignment(session, row, reason, utcnow())


def create_assignment(
    session: Session,
    task: ProductionTaskRow,
    actor: str,
    stage: AssignmentStage,
    source: AssignmentSource = "assign",
) -> Assignment:
    """Assign new work only to an eligible active person."""
    require_registered_assignee(session, actor)
    return _insert_assignment(session, task, actor, stage, source)


def preserve_personal_assignment(session: Session, task: ProductionTaskRow) -> Assignment:
    """Carry existing authorship through a tier upgrade independently of current account status."""
    if task.annotator_id is None:
        message = "Only existing personal authorship can be preserved"
        raise ValidationError(message)
    return _insert_assignment(session, task, task.annotator_id, "annotation", "preserved")


def _insert_assignment(
    session: Session,
    task: ProductionTaskRow,
    actor: str,
    stage: AssignmentStage,
    source: AssignmentSource,
) -> Assignment:
    project = require_mutable_project(session, task.project_id)
    if project.workflow_tier == "personal":
        message = "Personal projects do not create assignment records"
        raise ValidationError(message)
    existing = active_assignment(session, task.id, stage)
    if existing is not None:
        message = "Task already has an effective assignment for this stage"
        raise ConflictError(message)
    if stage == "review":
        require_separation(session, project, task, actor)
    now = utcnow()
    assignment = Assignment(
        id=new_id(),
        task_id=task.id,
        actor=actor,
        stage=stage,
        created_at=now,
        lease_expires_at=now + timedelta(minutes=project.lease_minutes),
        dispatch=source,
    )
    session.add(
        ProductionAssignmentRow(
            id=assignment.id,
            task_id=task.id,
            actor=actor,
            stage=stage,
            active=True,
            payload=assignment.model_dump(mode="json"),
            lease_expires_at=assignment.lease_expires_at.timestamp()
            if project.workflow_tier == "team"
            else None,
        )
    )
    if stage == "annotation":
        if task.round > 0 and task.annotator_id not in (None, actor):
            message = "Rework returns to the original annotator"
            raise ConflictError(message)
        task.annotator_id = actor
    transition_task(session, task, "in_progress" if stage == "annotation" else "in_review")
    record_project_member(session, task.project_id, actor)
    return assignment


def assign_tasks(session: Session, params: AssignTasksParams) -> tuple[Assignment, ...]:
    """Assign a homogeneous batch atomically, rejecting replacement of effective assignments."""
    if len(set(params.task_ids)) != len(params.task_ids):
        message = "Task assignment identities must be distinct"
        raise ValidationError(message)
    tasks = [require_task(session, task_id) for task_id in sorted(params.task_ids)]
    if len({task.project_id for task in tasks}) != 1:
        message = "One assignment operation must belong to a single project"
        raise ValidationError(message)
    expected = "pending" if params.stage == "annotation" else "submitted"
    if any(task.state != expected for task in tasks):
        message = "Task state does not permit assignment for this stage"
        raise ConflictError(message)
    if params.actor is None:
        message = "Named assignment requires actor"
        raise ValidationError(message)
    project = require_mutable_project(session, tasks[0].project_id)
    require_capacity(session, project, params.actor, params.stage, len(tasks))
    return tuple(create_assignment(session, task, params.actor, params.stage) for task in tasks)


def claim_task(session: Session, params: ClaimTaskParams, actor: str) -> ProductionTask:
    """Lock and claim the next task; concurrent claimers skip locked rows in PostgreSQL."""
    project = require_mutable_project(session, params.project_id)
    if project.workflow_tier == "personal":
        message = "Personal projects use next_task directly without assignments"
        raise ValidationError(message)
    require_stage_authority(session, actor, project.id, params.stage)
    require_claim_strategy(session, project, actor, params.stage)
    _validate_package(session, params)
    expected = "pending" if params.stage == "annotation" else "submitted"
    query = select(ProductionTaskRow).where(
        ProductionTaskRow.project_id == params.project_id,
        ProductionTaskRow.state == expected,
        ~select(ProductionAssignmentRow.id)
        .where(
            ProductionAssignmentRow.task_id == ProductionTaskRow.id,
            ProductionAssignmentRow.stage == params.stage,
            ProductionAssignmentRow.active.is_(True),
        )
        .exists(),
    )
    if params.stage == "annotation":
        query = query.where(
            or_(ProductionTaskRow.round == 0, ProductionTaskRow.annotator_id == actor)
        )
    elif project.workflow_tier == "team":
        query = exclude_own_work(query, actor)
    if params.package_id is not None:
        query = query.where(ProductionTaskRow.package_id == params.package_id)
    task = session.scalar(
        query.order_by(ProductionTaskRow.priority.desc(), ProductionTaskRow.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        message = "No available production task"
        raise NotFoundError(message)
    create_assignment(session, task, actor, params.stage, "claim")
    session.flush()
    return task_view(task)


def _validate_package(session: Session, params: ClaimTaskParams) -> None:
    if params.package_id is not None:
        package = session.get(ProductionPackageRow, params.package_id)
        if package is None or package.project_id != params.project_id:
            message = "Package was not found within the selected project"
            raise NotFoundError(message)


def release_task(session: Session, params: ReleaseTaskParams, actor: str) -> ProductionTask:
    """Release only the caller's effective assignment and return its stage to the queue."""
    task = require_task(session, params.task_id)
    require_mutable_project(session, task.project_id)
    require_stage_authority(session, actor, task.project_id, params.stage)
    row = active_assignment(session, task.id, params.stage)
    if row is None or row.actor != actor:
        message = "Only the effective assignment holder may release this task"
        raise AuthorizationError(message)
    expected = "in_progress" if params.stage == "annotation" else "in_review"
    if task.state != expected:
        message = "Submitted or approved annotations cannot be released"
        raise ConflictError(message)
    finish_assignment(session, task.id, params.stage, "released")
    transition_task(session, task, "pending" if params.stage == "annotation" else "submitted")
    return task_view(task)


def require_registered_assignee(session: Session, actor: str) -> None:
    """Require an active registered person once the instance has any identity records."""
    if session.scalar(select(UserRow.id).limit(1)) is None:
        return
    row = session.get(UserRow, actor)
    if row is None or User.model_validate(row.payload).status != "active":
        message = "Assignment actor must be a registered active user"
        raise ValidationError(message)


def require_stage_authority(
    session: Session,
    actor: str,
    project_id: str,
    stage: AssignmentStage,
) -> None:
    """Keep shared claim capability from granting annotation or review work in the other stage."""
    scopes = effective_scopes(session, actor, project_id).scopes
    required = "production:annotate" if stage == "annotation" else "production:review"
    if "*" not in scopes and required not in scopes:
        message = f"Missing server-authorized stage scope: {required}"
        raise AuthorizationError(message)
