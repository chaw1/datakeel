# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short transactional team-tier operations over generated fixtures, one commit each."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.actions.production_parameters import (
    ClaimTaskParams,
    ConfigureProjectParams,
    HeartbeatParams,
    ReviewTaskParams,
    RevokeAssignmentParams,
    SaveRevisionParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import Assignment
from datakeel.storage.production_assignments import claim_task
from datakeel.storage.production_projects import configure_project
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_reaper import renew_lease, revoke_assignment
from datakeel.storage.production_reviews import review_task, submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionAssignmentRow
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from collections.abc import Callable

    from datakeel.core.production_models import (
        AnnotationRevision,
        AssignmentStage,
        ProductionTask,
        Project,
    )
    from datakeel.storage.database import Database


def failure(operation: Callable[[], object]) -> Exception | None:
    """Return the raised domain error so mutation runs fail on an assertion, not a crash."""
    try:
        operation()
    except Exception as error:  # noqa: BLE001  # The caller asserts the exact error type.
        return error
    return None


def team_project(
    db: Database, count: int = 3, package_size: int = 100, **settings: object
) -> tuple[Project, tuple[ProductionTask, ...]]:
    """Create a generated team project and apply explicit team settings."""
    project, tasks = production_fixture(db, "team", count=count, package_size=package_size)
    if settings:
        with db.session() as session:
            db.lock_writes(session)
            project = configure_project(
                session,
                ConfigureProjectParams.model_validate(
                    {"request_id": new_id(), "project_id": project.id, **settings}
                ),
            )
            session.commit()
    return project, tasks


def claim(
    db: Database, project_id: str, actor: str, stage: AssignmentStage = "annotation"
) -> ProductionTask:
    """Claim the next task for one actor in its own transaction."""
    with db.session() as session:
        db.lock_writes(session)
        task = claim_task(
            session,
            ClaimTaskParams(request_id=new_id(), project_id=project_id, stage=stage),
            actor,
        )
        session.commit()
        return task


def save(db: Database, task_id: str, actor: str, label: str = "cat") -> AnnotationRevision:
    """Append one human revision on the current head."""
    task = get_task(db, task_id)
    with db.session() as session:
        db.lock_writes(session)
        revision = append_revision(
            session,
            require_task(session, task_id),
            SaveRevisionParams(
                request_id=new_id(),
                task_id=task_id,
                previous_revision_id=task.latest_revision_id,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id, annotator_id=actor, labels=(label,)
                ),
            ),
            actor,
        )
        session.commit()
        return revision


def submit(db: Database, task_id: str, actor: str) -> ProductionTask:
    """Submit the holder's current revision."""
    with db.session() as session:
        db.lock_writes(session)
        task = submit_task(session, SubmitTaskParams(request_id=new_id(), task_id=task_id), actor)
        session.commit()
        return task


def review(db: Database, task_id: str, actor: str, *, approve: bool = True) -> None:
    """Approve or return the current submitted revision."""
    task = get_task(db, task_id)
    with db.session() as session:
        db.lock_writes(session)
        review_task(
            session,
            ReviewTaskParams(
                request_id=new_id(),
                task_id=task_id,
                revision_id=task.latest_revision_id or "",
                decision="approve" if approve else "rework",
                issues=() if approve else ("Generated issue",),
            ),
            actor,
        )
        session.commit()


def heartbeat(
    db: Database, task_id: str, actor: str, stage: AssignmentStage = "annotation"
) -> Assignment:
    """Renew one lease in its own transaction."""
    with db.session() as session:
        db.lock_writes(session)
        assignment = renew_lease(
            session, HeartbeatParams(request_id=new_id(), task_id=task_id, stage=stage), actor
        )
        session.commit()
        return assignment


def revoke(
    db: Database, task_id: str, actor: str = "admin", stage: AssignmentStage = "annotation"
) -> Assignment:
    """Reclaim an assignment administratively."""
    with db.session() as session:
        db.lock_writes(session)
        assignment = revoke_assignment(
            session,
            RevokeAssignmentParams(
                request_id=new_id(), task_id=task_id, stage=stage, reason="Generated reclaim"
            ),
            actor,
        )
        session.commit()
        return assignment


def approve_all(db: Database, project_id: str, tasks: tuple[ProductionTask, ...]) -> None:
    """Annotate by one person and review by another for every task in the project."""
    for _ in tasks:
        task = claim(db, project_id, "annotator-a")
        save(db, task.id, "annotator-a")
        submit(db, task.id, "annotator-a")
    for _ in tasks:
        task = claim(db, project_id, "reviewer-b", "review")
        review(db, task.id, "reviewer-b")


def set_deadline(
    db: Database, task_id: str, seconds: float, stage: AssignmentStage = "annotation"
) -> Assignment:
    """Move the effective lease deadline relative to now, keeping payload and column in step."""
    deadline = utcnow() + timedelta(seconds=seconds)
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalars(
            select(ProductionAssignmentRow).where(
                ProductionAssignmentRow.task_id == task_id,
                ProductionAssignmentRow.stage == stage,
                ProductionAssignmentRow.active.is_(True),
            )
        ).one()
        assignment = Assignment.model_validate(row.payload).model_copy(
            update={"lease_expires_at": deadline}
        )
        row.payload = assignment.model_dump(mode="json")
        if row.lease_expires_at is not None:
            row.lease_expires_at = deadline.timestamp()
        session.commit()
        return assignment
