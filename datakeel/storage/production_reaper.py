# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Renew, reap and administratively reclaim team-tier assignments without losing revisions."""

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import HeartbeatParams, RevokeAssignmentParams
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import utcnow
from datakeel.core.production_models import Assignment, AssignmentStage, TaskState
from datakeel.core.production_team_models import LeaseReapResult
from datakeel.storage.database import Database
from datakeel.storage.production_assignments import active_assignment
from datakeel.storage.production_leases import (
    LEASED_STATES,
    RETURN_STATE,
    arm_lease,
    end_assignment,
    lease_expired,
    raise_if_reclaimed,
    record_release,
    require_live_lease,
    running_lease,
)
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow
from datakeel.storage.production_tasks import require_mutable_project, require_task, transition_task

REAP_BATCH = 500


def renew_lease(session: Session, params: HeartbeatParams, actor: str) -> Assignment:
    """Extend the caller's live team lease; an expired or lost lease is an explicit error."""
    task = require_task(session, params.task_id)
    project = require_mutable_project(session, task.project_id)
    if project.workflow_tier != "team":
        message = "Only team-tier projects use assignment leases and heartbeats"
        raise ValidationError(message)
    row = active_assignment(session, task.id, params.stage)
    if row is None or row.actor != actor:
        raise_if_reclaimed(session, task.id, actor, params.stage)
        message = "Only the effective assignment holder may renew its lease"
        raise AuthorizationError(message)
    if task.state not in LEASED_STATES[params.stage]:
        message = "This stage's lease is paused while the task is in another stage"
        raise ConflictError(message)
    now = utcnow()
    require_live_lease(row, now)
    arm_lease(row, project, now)
    session.flush()
    return Assignment.model_validate(row.payload)


def revoke_assignment(session: Session, params: RevokeAssignmentParams, actor: str) -> Assignment:
    """Return any holder's in-flight stage to the queue, including unregistered legacy holders."""
    task = require_task(session, params.task_id)
    project = require_mutable_project(session, task.project_id)
    if project.workflow_tier == "personal":
        message = "Personal projects have no assignments to revoke"
        raise ValidationError(message)
    row = active_assignment(session, task.id, params.stage)
    if row is None:
        message = "Task has no effective assignment for this stage"
        raise NotFoundError(message)
    if task.state not in LEASED_STATES[params.stage]:
        message = "Submitted or approved work cannot be revoked; reopen it instead"
        raise ConflictError(message)
    assignment = end_assignment(session, row, "revoked", utcnow())
    record_release(session, row, task.project_id, "revoked", released_by=actor, note=params.reason)
    _return(session, task, params.stage)
    return assignment


def lease_candidates(session: Session, now: datetime, limit: int) -> list[tuple[str, str]]:
    """List expired effective leases whose stage is still running, oldest deadline first."""
    statement = (
        select(ProductionAssignmentRow.id, ProductionAssignmentRow.task_id)
        .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
        .where(running_lease(), ProductionAssignmentRow.lease_expires_at <= now.timestamp())
        .order_by(ProductionAssignmentRow.lease_expires_at, ProductionAssignmentRow.id)
        .limit(limit)
    )
    return [(identifier, task_id) for identifier, task_id in session.execute(statement).all()]


def release_expired(
    session: Session, assignment_id: str, task_id: str, now: datetime
) -> bool | None:
    """Release one lease under its task lock; None means another transaction holds the task.

    Every assignment mutation locks its task first, so rereading the assignment after the
    lock decides exactly once whether it is still effective and still expired.
    """
    task = session.scalar(
        select(ProductionTaskRow)
        .where(ProductionTaskRow.id == task_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if task is None:
        return None
    row = session.scalar(
        select(ProductionAssignmentRow)
        .where(ProductionAssignmentRow.id == assignment_id)
        .execution_options(populate_existing=True)
    )
    if row is None or not row.active or not lease_expired(row, now):
        return False
    stage = cast("AssignmentStage", row.stage)
    if task.state not in LEASED_STATES[stage]:
        return False
    end_assignment(session, row, "expired", now)
    record_release(session, row, task.project_id, "expired", released_by="reaper")
    _return(session, task, stage)
    return True


def _return(session: Session, task: ProductionTaskRow, stage: AssignmentStage) -> None:
    target = cast("TaskState", RETURN_STATE[stage])
    if task.state != target:
        transition_task(session, task, target)


def reap_expired_leases(
    db: Database, *, now: datetime | None = None, limit: int = REAP_BATCH
) -> LeaseReapResult:
    """Release expired team leases once; concurrent and repeated passes are safe.

    Each release commits in its own short transaction. Holding one package's counters while
    locking another's would deadlock against claims that lock the same rows in sorted order.
    """
    moment = now or utcnow()
    with db.session() as session:
        candidates = lease_candidates(session, moment, limit)
    released: list[str] = []
    skipped = 0
    for assignment_id, task_id in candidates:
        with db.session() as session:
            db.lock_writes(session)
            outcome = release_expired(session, assignment_id, task_id, moment)
            session.commit()
        if outcome is None:
            skipped += 1
        elif outcome:
            released.append(assignment_id)
    return LeaseReapResult(
        released=len(released), skipped_locked=skipped, assignment_ids=tuple(released)
    )
