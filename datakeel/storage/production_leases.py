# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier lease primitives: arming, expiry checks and single recorded releases."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError
from datakeel.core.production_models import Assignment, AssignmentStage, Project
from datakeel.core.production_team_models import LeaseRelease
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow
from datakeel.storage.production_team_rows import ProductionLeaseReleaseRow

# A stage's lease only runs while its holder can still act; review keeps the annotation holder.
LEASED_STATES: dict[str, tuple[str, ...]] = {
    "annotation": ("pending", "in_progress"),
    "review": ("in_review",),
}
RETURN_STATE: dict[str, str] = {"annotation": "pending", "review": "submitted"}
# The indexed column stores a float; within this it is the recorded deadline itself.
_SAME_DEADLINE_SECONDS = 1e-3


def running_lease() -> ColumnElement[bool]:
    """Match effective assignments whose stage is still in progress, so their lease runs."""
    return and_(
        ProductionAssignmentRow.active.is_(True),
        ProductionAssignmentRow.lease_expires_at.is_not(None),
        or_(
            *(
                and_(ProductionAssignmentRow.stage == stage, ProductionTaskRow.state.in_(states))
                for stage, states in LEASED_STATES.items()
            )
        ),
    )


class LeaseExpiredError(ConflictError):
    """Report lease expiry explicitly instead of silently renewing or saving."""


def lease_expired(row: ProductionAssignmentRow, now: datetime) -> bool:
    """Treat an enforced lease as expired from its deadline onwards; NULL means unenforced."""
    return row.lease_expires_at is not None and row.lease_expires_at <= now.timestamp()


def require_live_lease(row: ProductionAssignmentRow, now: datetime) -> None:
    """Reject renewals and holder writes once the enforced deadline has passed."""
    if lease_expired(row, now):
        deadline = datetime.fromtimestamp(row.lease_expires_at or 0, tz=UTC).isoformat()
        message = (
            f"Assignment lease expired at {deadline}; the task will be reclaimed. "
            "Claim it again to continue"
        )
        raise LeaseExpiredError(message)


def arm_lease(row: ProductionAssignmentRow, project: Project, now: datetime) -> None:
    """Start or renew an enforced lease in the payload and its indexed column together."""
    deadline = now + timedelta(minutes=project.lease_minutes)
    assignment = Assignment.model_validate(row.payload).model_copy(
        update={"lease_expires_at": deadline}
    )
    row.payload = assignment.model_dump(mode="json")
    row.lease_expires_at = deadline.timestamp()


def restart_leases(session: Session, project: Project, now: datetime) -> None:
    """Start a full enforced lease at the upgrade moment for assignments made before the team tier.

    Their recorded expiry dates from the original claim and was never enforced, so enforcing it
    would reclaim work moments after an upgrade. Only the enforced deadline column is set; the
    assignment records stay as they were and the next heartbeat renews both.
    """
    deadline = (now + timedelta(minutes=project.lease_minutes)).timestamp()
    rows = session.scalars(
        select(ProductionAssignmentRow)
        .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
        .where(
            ProductionTaskRow.project_id == project.id,
            ProductionAssignmentRow.active.is_(True),
            ProductionAssignmentRow.lease_expires_at.is_(None),
        )
        .order_by(ProductionAssignmentRow.id)
    )
    for row in rows:
        row.lease_expires_at = deadline


def end_assignment(
    session: Session, row: ProductionAssignmentRow, reason: str, now: datetime
) -> Assignment:
    """Retire an assignment with its end time and reason, retaining the actor history."""
    assignment = Assignment.model_validate(row.payload).model_copy(
        update={"active": False, "ended_at": now, "end_reason": reason}
    )
    row.active, row.payload = False, assignment.model_dump(mode="json")
    session.flush()
    return assignment


def enforced_deadline(row: ProductionAssignmentRow, assignment: Assignment) -> datetime:
    """Return the deadline actually enforced, which a team upgrade may have restarted."""
    return effective_deadline(assignment.lease_expires_at, row.lease_expires_at)


def effective_deadline(recorded: datetime, enforced: float | None) -> datetime:
    """Prefer the enforced column; a lease restarted by a team upgrade keeps its old record."""
    if enforced is None or abs(enforced - recorded.timestamp()) < _SAME_DEADLINE_SECONDS:
        return recorded
    return datetime.fromtimestamp(enforced, tz=UTC)


def record_release(
    session: Session,
    row: ProductionAssignmentRow,
    project_id: str,
    reason: str,
    *,
    released_by: str,
    note: str = "",
) -> LeaseRelease:
    """Insert the single release fact; the assignment primary key forbids a second one."""
    assignment = Assignment.model_validate(row.payload)
    release = LeaseRelease.model_validate(
        {
            "assignment_id": assignment.id,
            "task_id": assignment.task_id,
            "project_id": project_id,
            "actor": assignment.actor,
            "stage": assignment.stage,
            "reason": reason,
            "lease_expires_at": enforced_deadline(row, assignment),
            "released_at": assignment.ended_at,
            "released_by": released_by,
            "note": note,
        }
    )
    session.add(
        ProductionLeaseReleaseRow(
            assignment_id=release.assignment_id,
            task_id=release.task_id,
            project_id=project_id,
            actor=release.actor,
            reason=reason,
            released_at=release.released_at.timestamp(),
            payload=release.model_dump(mode="json"),
        )
    )
    session.flush()
    return release


def raise_if_reclaimed(session: Session, task_id: str, actor: str, stage: AssignmentStage) -> None:
    """Explain a lost lease when the caller's latest assignment for this task expired."""
    rows = session.scalars(
        select(ProductionAssignmentRow).where(
            ProductionAssignmentRow.task_id == task_id,
            ProductionAssignmentRow.actor == actor,
            ProductionAssignmentRow.stage == stage,
        )
    )
    history = sorted(
        (Assignment.model_validate(row.payload) for row in rows),
        key=lambda item: (item.created_at, item.id),
    )
    if history and not history[-1].active and history[-1].end_reason == "expired":
        message = (
            f"Assignment lease expired at {history[-1].lease_expires_at.isoformat()} and the "
            "task was reclaimed; claim it again to continue"
        )
        raise LeaseExpiredError(message)
