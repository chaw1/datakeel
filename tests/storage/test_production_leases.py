# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier leases: arming, heartbeats, explicit expiry and a reaper that releases once."""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from datakeel.actions.production_parameters import UpgradeProjectParams
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_team_models import LeaseRelease
from datakeel.storage.production_leases import LeaseExpiredError, lease_expired
from datakeel.storage.production_projects import upgrade_project
from datakeel.storage.production_queries import get_task, list_assignments, list_revisions
from datakeel.storage.production_reaper import (
    lease_candidates,
    reap_expired_leases,
    release_expired,
)
from datakeel.storage.production_rows import ProductionAssignmentRow
from datakeel.storage.production_team_rows import ProductionLeaseReleaseRow
from tests.production_helpers import production_fixture
from tests.production_team_ops import (
    claim,
    failure,
    heartbeat,
    review,
    save,
    set_deadline,
    submit,
    team_project,
)

if TYPE_CHECKING:
    from datakeel.core.production_models import Assignment
    from datakeel.core.production_team_models import LeaseReapResult
    from datakeel.storage.database import Database


def _effective(db: Database, task_id: str, stage: str = "annotation") -> Assignment:
    return next(
        item for item in list_assignments(db, task_id) if item.active and item.stage == stage
    )


def _column(db: Database, assignment_id: str) -> float | None:
    with db.session() as session:
        return session.scalar(
            select(ProductionAssignmentRow.lease_expires_at).where(
                ProductionAssignmentRow.id == assignment_id
            )
        )


def _releases(db: Database) -> int:
    with db.session() as session:
        return int(session.scalar(select(func.count()).select_from(ProductionLeaseReleaseRow)) or 0)


def test_team_claim_arms_the_project_lease_and_heartbeat_renews_it(db: Database) -> None:
    """A claim is a lease of the project's length; a heartbeat moves the deadline forward."""
    project, _tasks = team_project(db, lease_minutes=7)
    before = utcnow()
    task = claim(db, project.id, "annotator-a")
    assignment = _effective(db, task.id)
    expected = before + timedelta(minutes=7)
    assert abs((assignment.lease_expires_at - expected).total_seconds()) < 5
    assert _column(db, assignment.id) == assignment.lease_expires_at.timestamp()
    assert assignment.dispatch == "claim"
    set_deadline(db, task.id, 30)
    renewed = heartbeat(db, task.id, "annotator-a")
    assert renewed.id == assignment.id
    assert renewed.lease_expires_at > utcnow() + timedelta(minutes=6)
    assert _column(db, assignment.id) == renewed.lease_expires_at.timestamp()


def test_group_assignments_keep_unenforced_leases_and_reject_heartbeats(db: Database) -> None:
    """Group and personal behaviour is unchanged: no enforced column and nothing to reap."""
    project, _tasks = production_fixture(db, "group")
    task = claim(db, project.id, "annotator-a")
    assignment = _effective(db, task.id)
    assert _column(db, assignment.id) is None
    result = reap_expired_leases(db, now=utcnow() + timedelta(days=30))
    assert result.released == 0
    assert _effective(db, task.id).id == assignment.id
    error = failure(lambda: heartbeat(db, task.id, "annotator-a"))
    assert isinstance(error, ValidationError)


def test_lease_expires_exactly_at_its_deadline(db: Database) -> None:
    """The deadline itself is expired; one microsecond earlier the lease is still live."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    assignment = _effective(db, task.id)
    with db.session() as session:
        row = session.get(ProductionAssignmentRow, assignment.id)
        assert row is not None
        deadline = assignment.lease_expires_at
        assert lease_expired(row, deadline)
        assert not lease_expired(row, deadline - timedelta(microseconds=1))
        row.lease_expires_at = None
        assert not lease_expired(row, deadline + timedelta(days=1))


def test_expired_lease_rejects_save_submit_and_heartbeat_explicitly(db: Database) -> None:
    """After the deadline the holder gets an explicit lease error, never a silent success."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    set_deadline(db, task.id, -1)
    for operation in (
        lambda: save(db, task.id, "annotator-a", "Cat"),
        lambda: submit(db, task.id, "annotator-a"),
        lambda: heartbeat(db, task.id, "annotator-a"),
    ):
        error = failure(operation)
        assert isinstance(error, LeaseExpiredError), error
        assert "expired" in str(error)
    assert len(list_revisions(db, task.id)) == 1
    assert get_task(db, task.id).state == "in_progress"


def test_reaper_returns_expired_work_to_pending_and_keeps_revisions(db: Database) -> None:
    """Reclaiming keeps the saved head; the old holder is told the lease was reclaimed."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    first = save(db, task.id, "annotator-a")
    set_deadline(db, task.id, -1)
    result = reap_expired_leases(db)
    assert result.released == 1
    current = get_task(db, task.id)
    assert (current.state, current.latest_revision_id, current.round) == ("pending", first.id, 0)
    ended = next(item for item in list_assignments(db, task.id) if item.actor == "annotator-a")
    assert (ended.active, ended.end_reason) == (False, "expired")
    assert ended.ended_at is not None
    for operation in (
        lambda: save(db, task.id, "annotator-a", "Cat"),
        lambda: heartbeat(db, task.id, "annotator-a"),
    ):
        error = failure(operation)
        assert isinstance(error, LeaseExpiredError), error
        assert "reclaimed" in str(error)
    claimed = claim(db, project.id, "annotator-c")
    assert claimed.id == task.id
    second = save(db, task.id, "annotator-c", "Cat")
    assert second.previous_revision_id == first.id
    assert [item.id for item in list_revisions(db, task.id)] == [first.id, second.id]
    assert reap_expired_leases(db).released == 0


def test_two_concurrent_reapers_release_every_expired_lease_exactly_once(db: Database) -> None:
    """Parallel reaper passes partition the expired leases; each gets one release record."""
    project, tasks = team_project(db, count=12)
    claimed = [claim(db, project.id, f"annotator-{index}").id for index in range(len(tasks))]
    for task_id in claimed:
        set_deadline(db, task_id, -1)
    barrier = threading.Barrier(2)
    results: list[LeaseReapResult] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            barrier.wait()
            results.append(reap_expired_leases(db, limit=50))
        except BaseException as error:  # noqa: BLE001  # Surface thread failures to the test.
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    released = [identifier for result in results for identifier in result.assignment_ids]
    assert len(released) == len(set(released)) == len(claimed)
    assert reap_expired_leases(db).released == 0
    assert _releases(db) == len(claimed)
    assert all(get_task(db, task_id).state == "pending" for task_id in claimed)


def test_stale_reaper_candidate_is_released_only_once(db: Database) -> None:
    """A second pass holding an old candidate list cannot release or record anything again."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    set_deadline(db, task.id, -1)
    moment = utcnow()
    with db.session() as session:
        stale = lease_candidates(session, moment, 10)
    assert len(stale) == 1
    assert reap_expired_leases(db, now=moment).released == 1
    outcomes: list[bool | None] = []
    with db.session() as session:
        db.lock_writes(session)
        error = failure(lambda: outcomes.append(release_expired(session, *stale[0], moment)))
        session.rollback()
    assert error is None, error
    assert outcomes == [False]
    assert _releases(db) == 1


def test_lease_renewed_after_listing_is_not_released(db: Database) -> None:
    """The reaper rereads under the task lock, so a heartbeat that wins the race keeps the work."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    set_deadline(db, task.id, -1)
    moment = utcnow()
    with db.session() as session:
        candidate = lease_candidates(session, moment, 10)[0]
    set_deadline(db, task.id, 300)
    with db.session() as session:
        db.lock_writes(session)
        outcome = release_expired(session, *candidate, moment)
        session.commit()
    assert outcome is False
    assert _effective(db, task.id).actor == "annotator-a"
    assert _releases(db) == 0


def test_reaper_crash_before_commit_is_safe_to_rerun(db: Database) -> None:
    """An interrupted pass leaves no trace; the next pass releases the lease once."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    set_deadline(db, task.id, -1)
    moment = utcnow()
    with db.session() as session:
        db.lock_writes(session)
        candidate = lease_candidates(session, moment, 10)[0]
        assert release_expired(session, *candidate, moment) is True
        session.rollback()
    assert get_task(db, task.id).state == "in_progress"
    assert _releases(db) == 0
    assert reap_expired_leases(db, now=moment).released == 1
    assert reap_expired_leases(db, now=moment).released == 0
    assert _releases(db) == 1


def test_review_lease_returns_task_to_the_review_queue(db: Database) -> None:
    """An expired review lease gives the submission back to reviewers without losing it."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    revision = save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    claim(db, project.id, "reviewer-b", "review")
    assert reap_expired_leases(db, now=utcnow() + timedelta(minutes=5)).released == 0
    set_deadline(db, task.id, -1, "review")
    assert reap_expired_leases(db).released == 1
    current = get_task(db, task.id)
    assert (current.state, current.latest_revision_id) == ("submitted", revision.id)
    error = failure(lambda: review(db, task.id, "reviewer-b"))
    assert isinstance(error, LeaseExpiredError), error
    claim(db, project.id, "reviewer-c", "review")
    review(db, task.id, "reviewer-c")
    assert get_task(db, task.id).state == "approved"


def test_annotation_lease_pauses_while_the_task_waits_for_review(db: Database) -> None:
    """The retained annotation holder is not reclaimed while the work is out of its hands."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    set_deadline(db, task.id, -1)
    assert reap_expired_leases(db).released == 0
    claim(db, project.id, "reviewer-b", "review")
    review(db, task.id, "reviewer-b", approve=False)
    holder = _effective(db, task.id)
    assert holder.actor == "annotator-a"
    assert holder.lease_expires_at > utcnow() + timedelta(minutes=5)
    save(db, task.id, "annotator-a", "Cat")
    assert get_task(db, task.id).round == 1


def test_upgrade_to_team_restarts_open_leases_at_the_upgrade(db: Database) -> None:
    """A group claim gets a full lease from the upgrade moment, not its old recorded deadline."""
    project, _tasks = production_fixture(db, "group")
    task = claim(db, project.id, "annotator-a")
    set_deadline(db, task.id, -60)
    assignment = _effective(db, task.id)
    before = utcnow()
    with db.session() as session:
        db.lock_writes(session)
        upgrade_project(
            session,
            UpgradeProjectParams(request_id=new_id(), project_id=project.id, workflow_tier="team"),
        )
        session.commit()
    after = utcnow()
    column = _column(db, assignment.id)
    assert column is not None
    lease = timedelta(minutes=project.lease_minutes)
    assert (before + lease).timestamp() <= column <= (after + lease).timestamp()
    assert _effective(db, task.id) == assignment
    assert reap_expired_leases(db, now=after).released == 0
    save(db, task.id, "annotator-a")
    reaped = reap_expired_leases(db, now=after + lease)
    assert reaped.released == 1
    with db.session() as session:
        release = session.get(ProductionLeaseReleaseRow, assignment.id)
        assert release is not None
        recorded = LeaseRelease.model_validate(release.payload).lease_expires_at
    assert abs(recorded.timestamp() - column) < 1e-3


def test_heartbeat_is_holder_only_and_stage_bound(db: Database) -> None:
    """Only the holder renews, and only while its own stage is running."""
    project, _tasks = team_project(db)
    task = claim(db, project.id, "annotator-a")
    assert isinstance(failure(lambda: heartbeat(db, task.id, "annotator-x")), AuthorizationError)
    save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    assert isinstance(failure(lambda: heartbeat(db, task.id, "annotator-a")), ConflictError)
