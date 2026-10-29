# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Repeated two-person claim races use real transactions in either isolated database fixture."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import TYPE_CHECKING

from datakeel.actions.production_parameters import ClaimTaskParams, ReleaseTaskParams
from datakeel.core.errors import NotFoundError
from datakeel.core.models import new_id
from datakeel.storage.production_assignments import claim_task, release_task
from datakeel.storage.production_queries import get_task, list_assignments, list_packages
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
