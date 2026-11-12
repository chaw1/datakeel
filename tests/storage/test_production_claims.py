# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Repeated two-person claim races use real transactions in either isolated database fixture."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from datakeel.actions.production_parameters import ClaimTaskParams, ReleaseTaskParams
from datakeel.core.errors import NotFoundError
from datakeel.core.models import new_id
from datakeel.dataset_store.display_order import task_key
from datakeel.storage.production_assignments import claim_task, release_task
from datakeel.storage.production_queries import get_task, list_assignments, list_packages
from datakeel.storage.production_rows import ProductionTaskRow
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_two_people_race_one_task_one_winner_repeated_one_hundred_times(db: Database) -> None:
    """Each of one hundred simultaneous claim races has exactly one effective assignment."""
    project, _ = production_fixture(db, "group", count=100, package_size=1)

    def contend(package_id: str, actor: str, barrier: Barrier) -> str | None:
        barrier.wait(timeout=20)
        try:
            with db.session() as session:
                db.lock_writes(session)
                task = claim_task(
                    session,
                    ClaimTaskParams(
                        request_id=new_id(),
                        project_id=project.id,
                        package_id=package_id,
                    ),
                    actor,
                )
                session.commit()
                return task.id
        except NotFoundError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        for package in list_packages(db, project.id):
            barrier = Barrier(2)
            futures = [
                pool.submit(contend, package.id, actor, barrier)
                for actor in ("annotator-a", "annotator-b")
            ]
            results = [future.result(timeout=30) for future in futures]
            winners = [result for result in results if result is not None]
            assert len(winners) == 1
            assignments = list_assignments(db, winners[0])
            assert len(assignments) == 1
            assert assignments[0].active


def test_losing_claimer_receives_another_available_task(db: Database) -> None:
    """A task already held by somebody else cannot block selection of the next available task."""
    project, _ = production_fixture(db, "group")
    claimed: list[str] = []
    for actor in ("annotator-a", "annotator-b"):
        with db.session() as session:
            db.lock_writes(session)
            result = claim_task(
                session, ClaimTaskParams(request_id=new_id(), project_id=project.id), actor
            )
            session.commit()
            claimed.append(result.id)
    assert len(set(claimed)) == 2


def test_claims_follow_the_task_list_display_order(db: Database) -> None:
    """Sequential claims return the list's next task; random identities never decide the order."""
    project, tasks = production_fixture(db, "group", count=2)
    claimed: list[str] = []
    for actor in ("annotator-a", "annotator-b"):
        with db.session() as session:
            db.lock_writes(session)
            result = claim_task(
                session, ClaimTaskParams(request_id=new_id(), project_id=project.id), actor
            )
            session.commit()
            claimed.append(result.id)
    assert claimed == [tasks[0].id, tasks[1].id]


def test_split_persists_display_ranks_in_list_order(db: Database) -> None:
    """The one-time split freezes the exact list order into indexed ranks across packages."""
    project, tasks = production_fixture(db, "group", count=5, package_size=2)
    with db.session() as session:
        key = task_key(session, project.id)
        rows = session.scalars(
            select(ProductionTaskRow).where(ProductionTaskRow.project_id == project.id)
        )
        ordered = sorted(rows, key=key)
        assert [row.display_rank for row in ordered] == list(range(len(tasks)))
        assert [row.id for row in ordered] == [task.id for task in tasks]


def test_legacy_null_ranks_are_backfilled_in_display_order_on_first_claim(db: Database) -> None:
    """Rows from before persisted ranks are ordered once, then claims follow the list exactly."""
    project, tasks = production_fixture(db, "group", count=4, package_size=2)
    with db.session() as session:
        session.execute(
            update(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project.id)
            .values(display_rank=None)
        )
        session.commit()
    claimed: list[str] = []
    for actor in ("annotator-a", "annotator-b", "annotator-c", "annotator-d"):
        with db.session() as session:
            db.lock_writes(session)
            result = claim_task(
                session, ClaimTaskParams(request_id=new_id(), project_id=project.id), actor
            )
            session.commit()
            claimed.append(result.id)
    assert claimed == [task.id for task in tasks]
    with db.session() as session:
        ranks = session.scalars(
            select(ProductionTaskRow.display_rank)
            .where(ProductionTaskRow.project_id == project.id)
            .order_by(ProductionTaskRow.display_rank)
        ).all()
    assert ranks == [0, 1, 2, 3]


def test_claim_priority_precedes_persisted_display_order(db: Database) -> None:
    """A higher-priority task is claimed first even when the list shows it later."""
    project, tasks = production_fixture(db, "group", count=3)
    with db.session() as session:
        row = session.get(ProductionTaskRow, tasks[-1].id)
        assert row is not None
        row.priority = 5
        session.commit()
    with db.session() as session:
        db.lock_writes(session)
        result = claim_task(
            session, ClaimTaskParams(request_id=new_id(), project_id=project.id), "annotator-a"
        )
        session.commit()
    assert result.id == tasks[-1].id


def test_release_keeps_revision_and_assignment_history(db: Database) -> None:
    """Release returns a task to pending and retains its assignment evidence."""
    project, _ = production_fixture(db, "group")
    with db.session() as session:
        task = claim_task(session, ClaimTaskParams(request_id="claim", project_id=project.id), "a")
        session.commit()
    with db.session() as session:
        release_task(session, ReleaseTaskParams(request_id="release", task_id=task.id), "a")
        session.commit()
    assert get_task(db, task.id).state == "pending"
    assert not list_assignments(db, task.id)[0].active
