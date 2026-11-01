# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A later turn's "刚才那个" is the previous turn's object, of any kind."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from datakeel.core.agent_models import ModelResponse
from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.intents.planner import ModelAccess, PlannerTurn, conversation_focus, plan_turn
from tests.intents.planning_support import steps, targets, two_projects

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def turned(db: Database, conversation: str, text: str, answer: dict[str, object]) -> IntentResult:
    """One turn of a conversation, the previous turns' objects in focus."""
    turn = PlannerTurn(
        text=text,
        actor="boss",
        context=PageContext(),
        conversation_id=conversation,
        focus=conversation_focus(db, conversation),
    )
    result = plan_turn(
        db,
        turn,
        complete=lambda _request: ModelResponse(content=json.dumps(answer)),
        access=ModelAccess(model="m", allowed=True),
    )
    assert result is not None
    return result


def test_those_tasks_in_a_later_turn_are_the_ones_just_assigned(db: Database) -> None:
    """Those tasks in a later turn are the ones just assigned."""
    _, _, tasks = two_projects(db)
    first = turned(
        db,
        "c1",
        "把南区车道最后两条派给小李",
        steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "小李"})),
    )
    assert targets(first) == tasks[4:6]
    later = turned(
        db,
        "c1",
        "把刚才那几条改派给小王",
        steps(("assign_tasks", {"task_ids": "刚才那几条", "actor": "小王"})),
    )
    assert later.kind == "plan", later.text
    assert targets(later) == tasks[4:6]


def test_that_person_in_a_later_turn_is_the_one_named_before(db: Database) -> None:
    """That person in a later turn is the one named before."""
    _, _, tasks = two_projects(db)
    turned(
        db,
        "c2",
        "Assign the last task of 南区车道 to 小李",
        steps(("assign_tasks", {"task_ids": tasks[5:6], "actor": "小李"})),
    )
    later = turned(
        db,
        "c2",
        "把第五条也派给他",
        steps(("assign_tasks", {"task_ids": tasks[4:5], "actor": "他"})),
    )
    assert later.kind == "plan", later.text
    assert later.chain is not None
    assert later.chain.steps[0].params["actor"] == "li"


def test_a_name_that_is_not_a_back_reference_is_resolved_as_usual(db: Database) -> None:
    """A name that is not a back reference is resolved as usual."""
    _, _, tasks = two_projects(db)
    turned(
        db,
        "c3",
        "把南区车道最后一条派给小李",
        steps(("assign_tasks", {"task_ids": tasks[5:6], "actor": "小李"})),
    )
    later = turned(
        db,
        "c3",
        "第五条派给小王",
        steps(("assign_tasks", {"task_ids": tasks[4:5], "actor": "小王"})),
    )
    assert later.chain is not None
    assert later.chain.steps[0].params["actor"] == "wang"


@pytest.mark.parametrize("copied", ["joined", "listed"])
def test_ids_copied_as_one_joined_string_are_still_several(db: Database, copied: str) -> None:
    """Ids the model copies from the focus line as one "a,b" string are still two tasks."""
    _, _, tasks = two_projects(db)
    turned(
        db,
        "c9",
        "Hand 小李 the last two tasks of 南区车道",
        steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "小李"})),
    )
    joined = ",".join(tasks[4:6])
    later = turned(
        db,
        "c9",
        "Actually, give those two to 小王 instead",
        steps(
            (
                "assign_tasks",
                {"task_ids": joined if copied == "joined" else [joined], "actor": "小王"},
            )
        ),
    )
    assert later.kind == "plan", later.text
    assert targets(later) == tasks[4:6]


def test_this_project_in_a_later_turn_is_the_one_just_changed(db: Database) -> None:
    """With no project on the page, "这个项目" in a later turn is the previous turn's."""
    north, _, _ = two_projects(db)
    first = turned(
        db,
        "c10",
        "North Crossing 每人最多同时做 3 条",
        steps(("configure_project", {"project_id": "North Crossing", "max_active_tasks": 3})),
    )
    assert first.kind == "plan", first.text
    later = turned(
        db,
        "c10",
        "再把这个项目升级成团队档",
        steps(("upgrade_project", {"project_id": "这个项目", "workflow_tier": "team"})),
    )
    assert later.kind == "plan", later.text
    assert later.chain is not None
    assert later.chain.steps[0].params["project_id"] == north.id


def test_a_name_that_matches_nothing_is_not_said_to_match_several(db: Database) -> None:
    """A name that matches nothing says nothing was found, then offers every choice."""
    two_projects(db)
    result = turned(
        db,
        "c11",
        "把火星基地项目升级成团队档",
        steps(("upgrade_project", {"project_id": "火星基地", "workflow_tier": "team"})),
    )
    assert result.clarification is not None, result.text
    assert "对应多个" not in result.clarification.question
    assert "没找到" in result.clarification.question
    assert len(result.clarification.candidates) > 1
