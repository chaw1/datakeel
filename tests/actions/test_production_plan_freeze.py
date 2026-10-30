# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Revoke and dispatch plans freeze only state, round and holders, not revision heads."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.actions.models import ExecuteRequest
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ConflictError
from datakeel.core.models import new_id
from datakeel.storage.production_queries import get_task, list_assignments
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, failure, heartbeat, save, submit, team_project
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan, ActionRun
    from datakeel.storage.database import Database

REASON = "Holder is unavailable"


def _execute(db: Database, plan: ActionPlan) -> ActionRun:
    return service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=plan.actor)
    )


def _model_draft(db: Database, task_id: str) -> None:
    task = get_task(db, task_id)
    with db.session() as session:
        db.lock_writes(session)
        append_revision(
            session,
            require_task(session, task_id),
            SaveRevisionParams(
                request_id=new_id(),
                task_id=task_id,
                previous_revision_id=task.latest_revision_id,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id, annotator_id="model", labels=("cat",)
                ),
                source="model",
                model_name="fake",
                model_version="1",
                confidence=0.5,
            ),
            "model",
        )
        session.commit()


def test_revoke_plan_survives_holder_saves_and_heartbeats(db: Database) -> None:
    """Autosaves and lease renewals after preparation do not invalidate a reclaim."""
    project, _tasks = team_project(db, count=1)
    runner = ServiceRunner(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    plan = runner.plan("revoke_assignment", {"task_id": task.id, "reason": REASON})
    save(db, task.id, "annotator-a")
    heartbeat(db, task.id, "annotator-a")
    latest = save(db, task.id, "annotator-a")
    error = failure(lambda: _execute(db, plan))
    assert error is None, error
    current = get_task(db, task.id)
    assert (current.state, current.latest_revision_id) == ("pending", latest.id)
    assert [item.end_reason for item in list_assignments(db, task.id)] == ["revoked"]


def test_revoke_plan_is_rejected_once_the_holder_submits(db: Database) -> None:
    """A submission after preparation changes the frozen state, so the reclaim is refused."""
    project, _tasks = team_project(db, count=1)
    runner = ServiceRunner(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    plan = runner.plan("revoke_assignment", {"task_id": task.id, "reason": REASON})
    submit(db, task.id, "annotator-a")
    error = failure(lambda: _execute(db, plan))
    assert isinstance(error, ConflictError), error
    assert "target state changed" in str(error)
    assert get_task(db, task.id).state == "submitted"


def test_dispatch_plan_survives_model_drafts_but_not_a_new_holder(db: Database) -> None:
    """A prediction import keeps an assignment plan valid; a claim of its task does not."""
    project, tasks = production_fixture(db, "group", count=2)
    runner = ServiceRunner(db)
    drafted = runner.plan("assign_tasks", {"task_ids": [tasks[0].id], "actor": "annotator-a"})
    _model_draft(db, tasks[0].id)
    error = failure(lambda: _execute(db, drafted))
    assert error is None, error
    assert [item.actor for item in list_assignments(db, tasks[0].id)] == ["annotator-a"]
    raced = runner.plan("assign_tasks", {"task_ids": [tasks[1].id], "actor": "annotator-a"})
    claimed = claim(db, project.id, "annotator-b")
    assert claimed.id == tasks[1].id
    stale = failure(lambda: _execute(db, raced))
    assert isinstance(stale, ConflictError), stale
    assert "target state changed" in str(stale)


def _reclaim_while_saving(db: Database, project_id: str, interval: float, wait: float) -> bool:
    """Save on a cadence in another thread; confirm a prepared reclaim after ``wait`` seconds."""
    runner = ServiceRunner(db)
    task = claim(db, project_id, "annotator-a")
    save(db, task.id, "annotator-a")
    stop = threading.Event()

    def autosave() -> None:
        while not stop.wait(interval):
            if failure(lambda: save(db, task.id, "annotator-a")) is not None:
                return

    worker = threading.Thread(target=autosave)
    worker.start()
    try:
        plan = runner.plan("revoke_assignment", {"task_id": task.id, "reason": REASON})
        time.sleep(wait)
        outcome = failure(lambda: _execute(db, plan))
    finally:
        stop.set()
        worker.join()
    return outcome is None and get_task(db, task.id).state == "pending"


def test_reclaim_confirmed_later_succeeds_while_the_holder_keeps_saving(db: Database) -> None:
    """The B9b cadence, time-scaled: saves every 0.2 s, confirmation 0.3 s after preparation."""
    project, _tasks = team_project(db, count=6)
    outcomes = [_reclaim_while_saving(db, project.id, 0.2, 0.3) for _ in range(6)]
    assert sum(outcomes) >= 5, outcomes
