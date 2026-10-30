# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reopening open work keeps its round, so the task can still be reassigned to someone else."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.production_models import ProductionTask
from datakeel.storage.production_queries import get_task, list_assignments
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.core.production_models import WorkflowTier
    from datakeel.storage.database import Database


def _reopen(runner: ServiceRunner, task_id: str) -> ProductionTask:
    details = runner("reopen_task", {"task_id": task_id, "reason": "Generated recheck"})
    return ProductionTask.model_validate(details.root, extra="ignore")


def _reassign(runner: ServiceRunner, task_id: str, actor: str) -> None:
    runner("revoke_assignment", {"task_id": task_id, "reason": "Generated handover"})
    runner("assign_tasks", {"task_ids": [task_id], "actor": actor})


@pytest.mark.parametrize("tier", ["group", "team"])
@pytest.mark.parametrize("started", [False, True])
def test_reopen_open_work_keeps_round_and_allows_reassignment(
    db: Database, tier: WorkflowTier, *, started: bool
) -> None:
    """Pending and in-progress reopen are no-ops on the round; another person then finishes."""
    _, tasks = production_fixture(db, tier, count=1)
    runner = ServiceRunner(db)
    task_id = tasks[0].id
    runner("assign_tasks", {"task_ids": [task_id], "actor": "annotator-a"})
    if started:
        save(db, task_id, "annotator-a")
    before = get_task(db, task_id)
    reopened = _reopen(runner, task_id)
    assert (reopened.state, reopened.round) == (before.state, 0)
    assert get_task(db, task_id).round == 0
    _reassign(runner, task_id, "annotator-b")
    active = [item for item in list_assignments(db, task_id) if item.active]
    assert [(item.actor, item.stage) for item in active] == [("annotator-b", "annotation")]
    save(db, task_id, "annotator-b")
    finished = submit(db, task_id, "annotator-b")
    assert (finished.state, finished.round, finished.annotator_id) == (
        "submitted",
        0,
        "annotator-b",
    )


def test_reopen_submitted_work_adds_one_round_and_returns_it_to_its_annotator(
    db: Database,
) -> None:
    """Only submitted or approved work sent back counts as a rework round."""
    project, tasks = production_fixture(db, "group", count=1)
    runner = ServiceRunner(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    reopened = _reopen(runner, task.id)
    assert (reopened.state, reopened.round) == ("pending", 1)
    assert tasks[0].id == task.id


def test_reopen_round_mutation_guard(db: Database) -> None:
    """One measured anchor: open work keeps round 0 and stays reassignable; finished work +1."""
    project, tasks = production_fixture(db, "group", count=2)
    runner = ServiceRunner(db)
    open_id = tasks[0].id
    runner("assign_tasks", {"task_ids": [open_id], "actor": "annotator-a"})
    save(db, open_id, "annotator-a")
    assert _reopen(runner, open_id).round == 0
    _reassign(runner, open_id, "annotator-b")
    assert submit(db, open_id, "annotator-b").round == 0
    done = claim(db, project.id, "annotator-c")
    save(db, done.id, "annotator-c")
    submit(db, done.id, "annotator-c")
    assert _reopen(runner, done.id).round == 1
