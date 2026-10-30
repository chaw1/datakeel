# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Personal and group task transactions, immutable histories and exact progress counters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ReopenTaskParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SubmitTaskParams,
    UpgradeProjectParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.models import new_id
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_projects import record_project_member, upgrade_project
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_assignments,
    list_reviews,
    list_revisions,
    next_task,
    project_progress,
)
from datakeel.storage.production_reviews import reopen_task, review_task, submit_task
from datakeel.storage.production_revisions import RevisionConflictError, append_revision
from datakeel.storage.production_rows import ProductionAssignmentRow
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from datakeel.core.production_models import AnnotationRevision, ProductionTask
    from datakeel.storage.database import Database


def save(
    db: Database,
    task: ProductionTask,
    actor: str = "local",
    previous: str | None = None,
) -> AnnotationRevision:
    """Save one generated human annotation through the actual transactional revision path."""
    with db.session() as session:
        db.lock_writes(session)
        result = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id=new_id(),
                task_id=task.id,
                previous_revision_id=previous,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id, annotator_id=actor, labels=("cat",)
                ),
            ),
            actor,
        )
        session.commit()
        return result


def test_personal_submit_approves_without_assignment_or_review(db: Database) -> None:
    """Personal saving and submission create revisions and counters without human assignments."""
    project, tasks = production_fixture(db)
    revision = save(db, tasks[0])
    with db.session() as session:
        task = submit_task(
            session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "local"
        )
        session.commit()
    assert task.state == "approved"
    assert task.approved_revision_id == revision.id
    assert list_assignments(db, task.id) == ()
    assert list_reviews(db, task.id) == ()
    progress = project_progress(db, project.id)
    assert {entry.state: entry.count for entry in progress.counts} == {
        "pending": 2,
        "in_progress": 0,
        "submitted": 0,
        "in_review": 0,
        "approved": 1,
        "finalized": 0,
    }
    assert project_progress(db, project.id, task.package_id).total == 3
    assert next_task(db, project.id) is not None


def test_stale_previous_pointer_returns_latest_and_never_overwrites(db: Database) -> None:
    """A stale client receives the authoritative head without changing either revision."""
    _, tasks = production_fixture(db)
    first = save(db, tasks[0])
    second = save(db, tasks[0], previous=first.id)
    with pytest.raises(RevisionConflictError) as rejected:
        save(db, tasks[0], previous=first.id)
    assert rejected.value.latest_revision == second
    assert get_task(db, tasks[0].id).latest_revision_id == second.id
    assert list_revisions(db, tasks[0].id) == (first, second)


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_revision_database_rejects_update_and_delete(db: Database, operation: str) -> None:
    """The immutable revision invariant survives direct SQL and alternate storage entry points."""
    _, tasks = production_fixture(db)
    revision = save(db, tasks[0])
    statement = (
        "UPDATE production_revisions SET actor='forged' WHERE id=:id"
        if operation == "UPDATE"
        else "DELETE FROM production_revisions WHERE id=:id"
    )
    rejected = False
    with db.session() as session:
        try:
            session.execute(text(statement), {"id": revision.id})
        except DBAPIError:
            rejected = True
    assert rejected, "Revision UPDATE and DELETE must be rejected by the database"
    assert list_revisions(db, tasks[0].id) == (revision,)


def test_database_enforces_one_active_assignment_per_task_stage(db: Database) -> None:
    """Direct duplicate insertion is rejected independently of application ownership checks."""
    _, tasks = production_fixture(db, "group")
    with db.session() as session:
        first = assign_tasks(
            session,
            AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="annotator-a"),
        )[0]
        session.commit()
    with db.session() as session:
        session.add(
            ProductionAssignmentRow(
                id=new_id(),
                task_id=tasks[0].id,
                actor="annotator-b",
                stage="annotation",
                active=True,
                payload=first.model_dump(mode="json"),
            )
        )
        rejected = False
        try:
            session.commit()
        except IntegrityError:
            rejected = True
        assert rejected, "The database must reject a duplicate active assignment"
    assert len(list_assignments(db, tasks[0].id)) == 1


def test_group_rework_retains_original_annotator_and_increments_round(db: Database) -> None:
    """Human rework points at an exact submitted revision and goes to its original task holder."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="worker")
        )
        session.commit()
    first = save(db, tasks[0], "worker")
    _submit_review(db, tasks[0].id, first.id, "rework")
    reworked = get_task(db, tasks[0].id)
    assert (reworked.state, reworked.round, reworked.annotator_id) == ("pending", 1, "worker")
    with pytest.raises(AuthorizationError):
        save(db, reworked, "other", previous=first.id)
    second = save(db, reworked, "worker", previous=first.id)
    _submit_review(db, reworked.id, second.id, "approve")
    assert get_task(db, reworked.id).approved_revision_id == second.id
    assert len(list_reviews(db, reworked.id)) == 2
    assert not list_assignments(db, reworked.id)[0].active
    assert project_progress(db, project.id).total == 3


def _submit_review(db: Database, task_id: str, revision_id: str, decision: str) -> None:
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id=new_id(), task_id=task_id), "worker")
        review_task(
            session,
            ReviewTaskParams(
                request_id=new_id(),
                task_id=task_id,
                revision_id=revision_id,
                decision="rework" if decision == "rework" else "approve",
                issues=("Correct the category",) if decision == "rework" else (),
            ),
            "worker",
        )
        session.commit()


def test_upgrade_retains_identity_revisions_and_rejects_downgrade(db: Database) -> None:
    """Tier changes affect workflow rules in place without rewriting any existing revision."""
    project, tasks = production_fixture(db)
    revision = save(db, tasks[0])
    for tier in ("group", "team"):
        with db.session() as session:
            upgrade_project(
                session,
                UpgradeProjectParams(
                    request_id=new_id(), project_id=project.id, workflow_tier=tier
                ),
            )
            session.commit()
        assert get_project(db, project.id).workflow_tier == tier
        assert list_revisions(db, tasks[0].id) == (revision,)
    with db.session() as session, pytest.raises(ValidationError, match="downgrade"):
        upgrade_project(
            session,
            UpgradeProjectParams(
                request_id="down", project_id=project.id, workflow_tier="personal"
            ),
        )


def test_reopen_before_finalize_preserves_revisions_and_reports_repeated_rework(
    db: Database,
) -> None:
    """Reopening approved work counts rounds while retaining append-only annotation history.

    P29b: only submitted or approved work sent back is a rework round, so each cycle submits
    (personal approval) before reopening.
    """
    project, tasks = production_fixture(db)
    revision = save(db, tasks[0])
    for _ in range(3):
        with db.session() as session:
            submit_task(
                session, SubmitTaskParams(request_id=new_id(), task_id=tasks[0].id), "local"
            )
            reopen_task(
                session,
                ReopenTaskParams(
                    request_id=new_id(), task_id=tasks[0].id, reason="Generated quality correction"
                ),
            )
            session.commit()
    progress = project_progress(db, project.id)
    assert progress.rework_task_ids == (tasks[0].id,)
    assert list_revisions(db, tasks[0].id) == (revision,)


def test_second_participant_suggests_review_once_without_upgrading(db: Database) -> None:
    """Adding a second participant yields one hint and does not silently change the project tier."""
    project, _ = production_fixture(db)
    with db.session() as session:
        assert record_project_member(session, project.id, "other")
        assert not record_project_member(session, project.id, "third")
        assert not record_project_member(session, project.id, "other")
        session.commit()
    assert get_project(db, project.id).workflow_tier == "personal"


def test_atomic_revision_compare_and_swap_blocks_stale_previous_pointer(db: Database) -> None:
    """The database pointer predicate alone prevents a stale save from replacing the head."""
    _, tasks = production_fixture(db)
    first = save(db, tasks[0])
    latest = None
    try:
        save(db, tasks[0])
    except RevisionConflictError as rejected:
        latest = rejected.latest_revision
    assert latest == first, "A stale previous pointer must return the current server revision"
    assert list_revisions(db, tasks[0].id) == (first,)


def test_next_task_prefers_original_annotators_rework_over_new_high_priority_work(
    db: Database,
) -> None:
    """A returned task is shown to its original annotator before newly available unassigned work."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="worker")
        )
        require_task(session, tasks[1].id).priority = 100
        session.commit()
    revision = save(db, tasks[0], "worker")
    _submit_review(db, tasks[0].id, revision.id, "rework")
    next_owned = next_task(db, project.id, "worker")
    assert next_owned is not None
    assert next_owned.id == tasks[0].id
    next_other = next_task(db, project.id, "other")
    assert next_other is not None
    assert next_other.id == tasks[1].id
