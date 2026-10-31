# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Per-person load limits hold under concurrent claims and dispatch on both databases."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.errors import ConflictError, DatakeelError
from datakeel.storage.production_dispatch_rules import active_loads, require_capacity
from datakeel.storage.production_load_locks import LoadLockError
from datakeel.storage.production_queries import get_project
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, failure, save, submit, team_project
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database

LIMIT = 3
REQUIREMENT = {"annotation_type": "classification", "domain": "retail", "min_level": 1}


def _approved(db: Database, plan: ActionPlan, actor: str) -> ActionPlan:
    if plan.requires_approval:
        service.approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    return plan


class _Outcomes:
    """Collect concurrent execution results, separating domain refusals from crashes."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.lock = threading.Lock()
        self.succeeded: list[str] = []
        self.refused: list[DatakeelError] = []
        self.crashed: list[BaseException] = []

    def execute(self, plan: ActionPlan, actor: str) -> None:
        try:
            run = service.execute_plan(
                self.db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor)
            )
        except DatakeelError as error:
            with self.lock:
                self.refused.append(error)
            return
        except BaseException as error:  # noqa: BLE001  # Surface database failures to the test.
            with self.lock:
                self.crashed.append(error)
            return
        with self.lock:
            self.succeeded.append(run.status)


def _warm_up(runner: ServiceRunner, project_id: str, actor: str) -> None:
    """Make the person a known member; a first appearance would serialize on the project row."""

    def claim_and_release() -> None:
        task_id = runner("claim_task", {"project_id": project_id}, actor).root["id"]
        runner("release_task", {"task_id": task_id}, actor)

    refused = failure(claim_and_release)
    assert refused is None, refused


def _run_together(*groups: tuple[list[ActionPlan], str, _Outcomes]) -> None:
    barrier = threading.Barrier(len(groups))

    def worker(plans: list[ActionPlan], actor: str, outcomes: _Outcomes) -> None:
        barrier.wait()
        for plan in plans:
            outcomes.execute(plan, actor)

    threads = [threading.Thread(target=worker, args=group) for group in groups]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)


def test_concurrent_claims_by_one_person_stop_exactly_at_the_limit(db: Database) -> None:
    """Twelve prepared claims fired at once by one person: exactly the limit succeed."""
    project, _tasks = team_project(db, count=16, max_active_tasks=LIMIT)
    runner = ServiceRunner(db)
    _warm_up(runner, project.id, "solo")
    plans = [runner.plan("claim_task", {"project_id": project.id}, "solo") for _ in range(12)]
    outcomes = _Outcomes(db)
    _run_together(*(([plan], "solo", outcomes) for plan in plans))
    assert outcomes.crashed == []
    assert len(outcomes.succeeded) == LIMIT
    assert len(outcomes.refused) == len(plans) - LIMIT
    assert all(isinstance(error, ConflictError) for error in outcomes.refused)
    assert "adding 1 would exceed the limit of 3" in str(outcomes.refused[0])
    with db.session() as session:
        assert active_loads(session, project.id, "annotation") == {"solo": LIMIT}


def test_concurrent_claims_after_submissions_still_stop_exactly_at_the_limit(
    db: Database,
) -> None:
    """Submitted work is not open; twelve claims fired at once then add exactly the limit."""
    project, _tasks = team_project(db, count=20, max_active_tasks=LIMIT)
    runner = ServiceRunner(db)
    _warm_up(runner, project.id, "solo")
    for _ in range(LIMIT):
        task = claim(db, project.id, "solo")
        save(db, task.id, "solo")
        submit(db, task.id, "solo")
    plans = [runner.plan("claim_task", {"project_id": project.id}, "solo") for _ in range(12)]
    outcomes = _Outcomes(db)
    _run_together(*(([plan], "solo", outcomes) for plan in plans))
    assert outcomes.crashed == []
    assert len(outcomes.succeeded) == LIMIT
    assert len(outcomes.refused) == len(plans) - LIMIT
    assert all(isinstance(error, ConflictError) for error in outcomes.refused)
    with db.session() as session:
        assert active_loads(session, project.id, "annotation") == {"solo": LIMIT}


def test_skill_dispatch_racing_three_claimers_keeps_everyone_within_the_limit(
    db: Database,
) -> None:
    """A manager's skill dispatch and three people's claims run at once; nobody exceeds three."""
    project, tasks = production_fixture(db, "team", count=24)
    runner = ServiceRunner(db)
    people = ("t1", "t2", "t3")
    register(runner, project.id, dict.fromkeys(people, "annotator") | {"pm": "project_manager"})
    grant_skills(runner, dict.fromkeys(people, 3))
    runner(
        "configure_project",
        {
            "project_id": project.id,
            "skill_requirement": REQUIREMENT,
            "dispatch_strategy": "skill",
            "max_active_tasks": LIMIT,
        },
        "pm",
    )
    for actor in people:
        _warm_up(runner, project.id, actor)
    outcomes = _Outcomes(db)
    claims = [
        ([runner.plan("claim_task", {"project_id": project.id}, actor) for _ in range(4)], actor)
        for actor in people
    ]
    dispatch = _approved(
        db,
        runner.plan(
            "assign_tasks",
            {"task_ids": [task.id for task in tasks], "strategy": "skill"},
            "pm",
        ),
        "pm",
    )
    _run_together(
        *((plans, actor, outcomes) for plans, actor in claims), ([dispatch], "pm", outcomes)
    )
    assert outcomes.crashed == []
    with db.session() as session:
        loads = active_loads(session, project.id, "annotation")
    assert set(loads) <= set(people)
    assert all(load <= LIMIT for load in loads.values()), loads
    assert sum(loads.values()) == LIMIT * len(people)
    assert get_project(db, project.id).max_active_tasks == LIMIT


def test_counting_a_load_without_the_person_lock_is_refused(db: Database) -> None:
    """A dispatch path that forgets to serialize on the person fails loudly on any database."""
    project, _tasks = team_project(db, count=1, max_active_tasks=LIMIT)
    with db.session() as session, pytest.raises(LoadLockError, match="solo"):
        require_capacity(session, project, "solo", "annotation")
