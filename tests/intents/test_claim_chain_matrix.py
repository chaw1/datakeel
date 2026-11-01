# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A small claim/dispatch chain matrix, with every retained chain executed to its terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.intent_models import PageContext
from tests.intents.planning_support import planned, steps, two_projects
from tests.intents.support import run_to_end
from tests.production_team_ops import save
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database

Action = tuple[str, dict[str, object]]
CASES = (
    "claim-assign-over",
    "assign-claim-over",
    "assign-assign-over",
    "release-claim",
    "release-only-free",
    "release-claim-claim-over",
    "revoke-claim",
    "claim-revoke",
    "actor-isolation",
    "stage-isolation",
    "project-isolation",
    "submit-claim-conservative",
)


def _actions(name: str, north: str, south: str, tasks: list[str]) -> tuple[list[Action], str, int]:
    claim: Action = ("claim_task", {"project_id": south})
    assign: Action = ("assign_tasks", {"task_ids": [tasks[4]], "actor": "boss"})
    another: Action = ("assign_tasks", {"task_ids": [tasks[5]], "actor": "boss"})
    release: Action = ("release_task", {"task_id": tasks[0]})
    revoke: Action = ("revoke_assignment", {"task_id": tasks[0], "reason": "matrix"})
    to_li: Action = ("assign_tasks", {"task_ids": [tasks[4]], "actor": "li"})
    review: Action = ("claim_task", {"project_id": south, "stage": "review"})
    submit: Action = ("submit_task", {"task_id": tasks[0]})
    other: Action = ("claim_task", {"project_id": north})
    scenarios: dict[str, tuple[list[Action], str, int]] = {
        "claim-assign-over": ([claim, another], "boss", 1),
        "assign-claim-over": ([assign, claim], "boss", 1),
        "assign-assign-over": ([assign, another], "boss", 1),
        "release-claim": ([release, claim], "wang", 2),
        "release-only-free": ([release, claim], "wang", 2),
        "release-claim-claim-over": ([release, claim, claim], "wang", 2),
        "revoke-claim": ([revoke, claim], "boss", 2),
        "claim-revoke": ([claim, revoke], "boss", 2),
        "actor-isolation": ([to_li, claim], "boss", 2),
        "stage-isolation": ([claim, review], "boss", 2),
        "project-isolation": ([other, claim], "boss", 2),
        "submit-claim-conservative": ([submit, claim], "wang", 1),
    }
    return scenarios[name]


@pytest.mark.parametrize("name", CASES)
def test_claim_dispatch_chain_matrix(db: Database, name: str) -> None:
    """Unsafe later steps are set aside; retained and legal chains all execute successfully."""
    north, south, tasks = two_projects(db)
    run = ServiceRunner(db)
    run("configure_project", {"project_id": south.id, "max_active_tasks": 2}, "boss")
    if name in {"claim-assign-over", "assign-claim-over", "assign-assign-over"}:
        run("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
    if name == "actor-isolation":
        run("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
    if name == "stage-isolation":
        run("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
        run("release_task", {"task_id": tasks[2], "stage": "review"}, "zhao")
    if name == "submit-claim-conservative":
        save(db, tasks[0], "wang")
    if name == "release-only-free":
        run("assign_tasks", {"task_ids": tasks[4:6], "actor": "li"}, "boss")
    actions, actor, expected = _actions(name, north.id, south.id, tasks)
    answer = steps(*actions)
    context = PageContext() if name == "project-isolation" else PageContext(project_id=south.id)
    text = "North Crossing 和 南区车道各领一个" if name == "project-isolation" else "混合领取矩阵"
    result = planned(db, text, [answer], context, actor=actor)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert len(result.chain.steps) == expected, result.text
    finished = run_to_end(db, result.chain, actor)
    assert finished.status == "succeeded", finished
    assert all(step.status == "succeeded" for step in finished.steps), finished
    if expected < len(actions):
        assert "没有做" in result.text, result.text
