# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team separation of duties holds across claims, assignments, reassignment, roles and reopen."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.production_parameters import AssignTasksParams, ReopenTaskParams
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.models import new_id
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_reviews import reopen_task
from tests.production_helpers import production_fixture
from tests.production_team_ops import (
    claim,
    failure,
    review,
    revoke,
    save,
    submit,
    team_project,
)
from tests.production_team_support import ServiceRunner, register

if TYPE_CHECKING:
    from datakeel.core.production_models import Assignment
    from datakeel.storage.database import Database


def _assign(db: Database, task_id: str, actor: str, stage: str = "review") -> Assignment:
    with db.session() as session:
        db.lock_writes(session)
        (assignment,) = assign_tasks(
            session,
            AssignTasksParams.model_validate(
                {"request_id": new_id(), "task_ids": [task_id], "actor": actor, "stage": stage}
            ),
        )
        session.commit()
        return assignment


def _reopen(db: Database, task_id: str) -> None:
    with db.session() as session:
        db.lock_writes(session)
        reopen_task(
            session,
            ReopenTaskParams(request_id=new_id(), task_id=task_id, reason="Generated recheck"),
        )
        session.commit()


def _annotate(db: Database, project_id: str, actor: str) -> str:
    task = claim(db, project_id, actor)
    save(db, task.id, actor)
    submit(db, task.id, actor)
    return task.id


def test_team_annotator_cannot_claim_be_assigned_or_review_own_task(db: Database) -> None:
    """Every review entry point refuses the annotator; another person reviews normally."""
    project, _tasks = team_project(db, count=1)
    task_id = _annotate(db, project.id, "annotator-a")
    missing = failure(lambda: claim(db, project.id, "annotator-a", "review"))
    assert isinstance(missing, NotFoundError), missing
    for operation in (
        lambda: _assign(db, task_id, "annotator-a"),
        lambda: review(db, task_id, "annotator-a"),
    ):
        error = failure(operation)
        assert isinstance(error, AuthorizationError), error
        assert "Separation of duties" in str(error)
    assert get_task(db, task_id).state == "submitted"
    claim(db, project.id, "reviewer-b", "review")
    review(db, task_id, "reviewer-b")
    assert get_task(db, task_id).state == "approved"


def test_reassignment_does_not_launder_an_earlier_annotator(db: Database) -> None:
    """A person whose work was revoked mid-round still annotated the task and cannot review it."""
    project, _tasks = team_project(db, count=1)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    revoke(db, task.id)
    finished = _annotate(db, project.id, "annotator-c")
    assert finished == task.id
    assert get_task(db, task.id).annotator_id == "annotator-c"
    for actor in ("annotator-a", "annotator-c"):
        assert isinstance(
            failure(lambda actor=actor: _assign(db, task.id, actor)), AuthorizationError
        )
        queue = failure(lambda actor=actor: claim(db, project.id, actor, "review"))
        assert isinstance(queue, NotFoundError), queue
    claim(db, project.id, "reviewer-b", "review")
    review(db, task.id, "reviewer-b")


def test_holding_without_saving_still_counts_as_annotating(db: Database) -> None:
    """Claiming the annotation stage is enough to be excluded from reviewing that task."""
    project, _tasks = team_project(db, count=1)
    task = claim(db, project.id, "annotator-a")
    revoke(db, task.id)
    _annotate(db, project.id, "annotator-c")
    error = failure(lambda: review(db, task.id, "annotator-a"))
    assert isinstance(error, AuthorizationError), error


def test_reopen_round_keeps_earlier_round_annotators_out_of_review(db: Database) -> None:
    """After reopening, the round-zero annotator still cannot review round one."""
    project, _tasks = team_project(db, count=1)
    task_id = _annotate(db, project.id, "annotator-a")
    claim(db, project.id, "reviewer-b", "review")
    review(db, task_id, "reviewer-b")
    _reopen(db, task_id)
    assert get_task(db, task_id).round == 1
    claim(db, project.id, "annotator-a")
    save(db, task_id, "annotator-a")
    submit(db, task_id, "annotator-a")
    error = failure(lambda: review(db, task_id, "annotator-a"))
    assert isinstance(error, AuthorizationError), error
    claim(db, project.id, "reviewer-b", "review")
    review(db, task_id, "reviewer-b")
    assert get_task(db, task_id).state == "approved"


def test_role_change_does_not_lift_separation(db: Database) -> None:
    """Becoming a reviewer later grants review scope but never over one's own annotations."""
    project, _tasks = team_project(db, count=2)
    runner = ServiceRunner(db)
    register(runner, project.id, {"ann": "annotator", "qa": "reviewer"})
    task_id = _annotate(db, project.id, "ann")
    binding = {"user_id": "ann", "project_id": project.id}
    runner("manage_users", {"operation": "unbind_role", "role_id": "annotator", **binding})
    runner("manage_users", {"operation": "bind_role", "role_id": "reviewer", **binding})
    queue = failure(lambda: claim(db, project.id, "ann", "review"))
    assert isinstance(queue, NotFoundError), queue
    error = failure(lambda: review(db, task_id, "ann"))
    assert isinstance(error, AuthorizationError), error
    plan = failure(
        lambda: runner("assign_tasks", {"task_ids": [task_id], "actor": "ann", "stage": "review"})
    )
    assert isinstance(plan, AuthorizationError), plan
    claim(db, project.id, "qa", "review")
    review(db, task_id, "qa")


def test_group_tier_still_allows_self_review(db: Database) -> None:
    """Group projects keep P29 behaviour: one person may annotate and then review."""
    project, _tasks = production_fixture(db, "group", count=1)
    task_id = _annotate(db, project.id, "annotator-a")
    reviewed = claim(db, project.id, "annotator-a", "review")
    assert reviewed.id == task_id
    review(db, task_id, "annotator-a")
    assert get_task(db, task_id).state == "approved"
