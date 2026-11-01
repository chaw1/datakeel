# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Single-step dispatch checks match execution for task state and effective assignments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.storage.production_queries import get_task
from tests.intents.planning_support import planned, steps, two_projects
from tests.intents.support import run_to_end
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _assign(
    db: Database, project: str, task: str, actor: str, stage: str = "annotation"
) -> IntentResult:
    params: dict[str, object] = {"task_ids": [task], "actor": actor, "stage": stage}
    return planned(
        db,
        "重新规划派单",
        [steps(("assign_tasks", params))],
        PageContext(project_id=project),
        actor="boss",
    )


def test_claim_then_replan_assign_rejects_in_progress_work_but_pending_work_runs(
    db: Database,
) -> None:
    """The claimed task cannot be assigned again; a free pending task can still be assigned."""
    _, south, tasks = two_projects(db)
    claim = ("claim_task", {"project_id": south.id})
    assign = ("assign_tasks", {"task_ids": [tasks[4]], "actor": "li"})
    initial = planned(
        db,
        "先领取再派单",
        [steps(claim, assign)],
        PageContext(project_id=south.id),
        actor="boss",
    )
    assert initial.chain is not None
    assert len(initial.chain.steps) == 1
    assert run_to_end(db, initial.chain, "boss").status == "succeeded"
    assert get_task(db, tasks[4]).state == "in_progress"
    refused = _assign(db, south.id, tasks[4], "li")
    assert refused.chain is None, refused.text
    assert "不能派单" in refused.text, refused.text
    legal = _assign(db, south.id, tasks[5], "li")
    assert legal.kind == "plan", legal.text
    assert legal.chain is not None
    assert run_to_end(db, legal.chain, "boss").status == "succeeded"


def test_review_dispatch_requires_submitted_unheld_work(db: Database) -> None:
    """Submitted unheld review work runs; in-review, held or not-yet-submitted work is refused."""
    _, south, tasks = two_projects(db)
    run = ServiceRunner(db)
    run("release_task", {"task_id": tasks[2], "stage": "review"}, "zhao")
    legal = _assign(db, south.id, tasks[2], "zhao", "review")
    assert legal.kind == "plan", legal.text
    assert legal.chain is not None
    assert run_to_end(db, legal.chain, "boss").status == "succeeded"
    assert get_task(db, tasks[2]).state == "in_review"
    held = _assign(db, south.id, tasks[2], "zhao", "review")
    assert held.chain is None, held.text
    assert "不能派单" in held.text, held.text
    pending = _assign(db, south.id, tasks[4], "zhao", "review")
    assert pending.chain is None, pending.text
    assert "不能派单" in pending.text, pending.text
