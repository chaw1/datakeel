# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""State-dependent suffixes defer, then legal next steps replan against the new database state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.intent_models import PageContext
from tests.intents.planning_support import planned, steps, two_projects
from tests.intents.support import run_to_end
from tests.production_team_ops import review, save
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database

Action = tuple[str, dict[str, object]]
Scenario = tuple[list[Action], str, int, list[bool]]
LIMIT_ONE = frozenset(
    {
        "claim-claim-over",
        "claim-assign-over",
        "assign-claim-over",
        "claim-release-claim",
        "claim-revoke-claim",
        "assign-release-claim",
        "claim-release-assign",
        "actor-isolation",
        "stage-isolation",
    }
)
CASES = (
    "claim-claim-over",
    "claim-assign-over",
    "assign-claim-over",
    "release-claim-claim-over",
    "upgrade-assign-claim",
    "release-release",
    "revoke-revoke",
    "assign-assign",
    "claim-assign-claimed",
    "claim-release-claim",
    "claim-revoke-claim",
    "assign-release",
    "assign-revoke",
    "revoke-assign",
    "assign-release-claim",
    "claim-release-assign",
    "release-claim",
    "revoke-claim",
    "actor-isolation",
    "stage-isolation",
    "project-isolation",
    "submit-claim",
    "reopen-claim",
    "review-claim",
)


def _scenario(name: str, north: str, south: str, tasks: list[str]) -> Scenario:
    claim: Action = ("claim_task", {"project_id": south})
    assign: Action = ("assign_tasks", {"task_ids": [tasks[4]], "actor": "boss"})
    another: Action = ("assign_tasks", {"task_ids": [tasks[5]], "actor": "boss"})
    release: Action = ("release_task", {"task_id": tasks[0]})
    release_new: Action = ("release_task", {"task_id": tasks[4]})
    revoke: Action = ("revoke_assignment", {"task_id": tasks[0], "reason": "matrix"})
    revoke_new: Action = ("revoke_assignment", {"task_id": tasks[4], "reason": "matrix"})
    review_claim: Action = ("claim_task", {"project_id": south, "stage": "review"})
    upgrade: Action = ("upgrade_project", {"project_id": north, "workflow_tier": "team"})
    north_claim: Action = ("claim_task", {"project_id": north})
    scenarios: dict[str, Scenario] = {
        "claim-claim-over": ([claim, claim], "li", 1, [False]),
        "claim-assign-over": ([claim, another], "boss", 1, [False]),
        "assign-claim-over": ([assign, claim], "boss", 1, [False]),
        "release-claim-claim-over": ([release, claim, claim], "wang", 1, [True, False]),
        "upgrade-assign-claim": ([upgrade, north_claim], "boss", 1, [False]),
        "release-release": ([release, release], "wang", 1, []),
        "revoke-revoke": ([revoke, revoke], "boss", 1, []),
        "assign-assign": ([assign, assign], "boss", 1, []),
        "claim-assign-claimed": (
            [claim, ("assign_tasks", {"task_ids": [tasks[4]], "actor": "li"})],
            "boss",
            1,
            [],
        ),
        "claim-release-claim": ([claim, release_new, claim], "boss", 1, [True, True]),
        "claim-revoke-claim": ([claim, revoke_new, claim], "boss", 1, [True, True]),
        "assign-release": ([assign, release_new], "boss", 1, [True]),
        "assign-revoke": ([assign, revoke_new], "boss", 1, [True]),
        "revoke-assign": (
            [revoke, ("assign_tasks", {"task_ids": [tasks[0]], "actor": "boss"})],
            "boss",
            1,
            [True],
        ),
        "assign-release-claim": ([assign, release_new, claim], "boss", 1, [True, True]),
        "claim-release-assign": ([claim, release_new, another], "boss", 1, [True, True]),
        "release-claim": ([release, claim], "wang", 1, [True]),
        "revoke-claim": ([revoke, claim], "boss", 1, [True]),
        "actor-isolation": (
            [("assign_tasks", {"task_ids": [tasks[4]], "actor": "li"}), claim],
            "boss",
            1,
            [True],
        ),
        "stage-isolation": ([claim, review_claim], "boss", 1, [True]),
        "project-isolation": ([north_claim, claim], "boss", 2, []),
        "submit-claim": ([("submit_task", {"task_id": tasks[0]}), claim], "wang", 1, [True]),
        "reopen-claim": ([("reopen_task", {"task_id": tasks[2]}), claim], "boss", 1, [True]),
        "review-claim": (
            [("review_task", {"task_id": tasks[2], "decision": "approve"}), review_claim],
            "zhao",
            1,
            [],
        ),
    }
    return scenarios[name]


def _execute(db: Database, project: str, action: Action, actor: str, *, legal: bool) -> None:
    result = planned(db, "重新规划", [steps(action)], PageContext(project_id=project), actor=actor)
    if not legal:
        assert result.chain is None, result.text
        return
    assert result.kind == "plan", result.text
    assert result.chain is not None
    finished = run_to_end(db, result.chain, actor)
    assert finished.status == "succeeded", finished


@pytest.mark.parametrize("name", CASES)
def test_defer_then_replan_matrix(db: Database, name: str) -> None:
    """The safe prefix runs, the suffix is explicitly deferred, and legal next steps replan."""
    north, south, tasks = two_projects(db)
    run = ServiceRunner(db)
    run("configure_project", {"project_id": south.id, "max_active_tasks": 2}, "boss")
    if name in LIMIT_ONE:
        run("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
    if name == "upgrade-assign-claim":
        run("configure_project", {"project_id": north.id, "dispatch_strategy": "assign"}, "boss")
    if name == "stage-isolation":
        run("release_task", {"task_id": tasks[2], "stage": "review"}, "zhao")
    if name == "submit-claim":
        save(db, tasks[0], "wang")
    if name == "reopen-claim":
        review(db, tasks[2], "zhao", approve=True)
    project = north.id if name == "upgrade-assign-claim" else south.id
    actions, actor, prefix, replan = _scenario(name, north.id, south.id, tasks)
    context = PageContext() if name == "project-isolation" else PageContext(project_id=project)
    text = (
        "North Crossing 和 南区车道各领一个" if name == "project-isolation" else "动作链重规划矩阵"
    )
    result = planned(db, text, [steps(*actions)], context, actor=actor)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert len(result.chain.steps) == prefix, result.text
    if prefix < len(actions):
        assert "上一步完成后再规划" in result.text, result.text
        assert any("上一步完成后再规划" in note for note in result.chain.notes), result.chain.notes
    finished = run_to_end(db, result.chain, actor)
    assert finished.status == "succeeded", finished
    assert all(step.status == "succeeded" for step in finished.steps), finished
    for action, legal in zip(actions[prefix:], replan, strict=False):
        _execute(db, project, action, actor, legal=legal)


def test_deferred_note_is_explicit_in_english(db: Database) -> None:
    """The existing result and chain notes say deferred for replanning, without new API fields."""
    _, south, tasks = two_projects(db)
    release = ("release_task", {"task_id": tasks[0]})
    result = planned(
        db,
        "Release it, then release it again",
        [steps(release, release)],
        PageContext(project_id=south.id),
        actor="wang",
    )
    assert result.chain is not None
    assert len(result.chain.steps) == 1
    assert "deferred for replanning" in result.text, result.text
    assert any("deferred for replanning" in note for note in result.chain.notes)
    assert run_to_end(db, result.chain, "wang").status == "succeeded"
