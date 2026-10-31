# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3 world: two named projects whose identities do not follow the list order."""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.storage.production_queries import list_tasks
from datakeel.storage.production_rows import ProductionProjectRow
from tests.production_helpers import production_fixture
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    import pytest

    from datakeel.core.intent_models import IntentResult, PageContext
    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database

NORTH, SOUTH = "North Crossing", "南区车道"
PEOPLE = (("wang", "小王", "annotator"), ("li", "小李", "annotator"), ("zhao", "小赵", "reviewer"))


def descending_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Projects, packages and tasks get identities that sort against their creation order."""
    counter = itertools.count(99999999, -1)

    def fresh() -> str:
        return f"{next(counter):08d}-0000-4000-8000-000000000000"

    monkeypatch.setattr("datakeel.storage.production_projects.new_id", fresh)


def _named(db: Database, project: Project, name: str) -> Project:
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(ProductionProjectRow, project.id)
        assert row is not None
        row.payload = {**row.payload, "name": name}
        session.commit()
    return project.model_copy(update={"name": name})


def two_projects(db: Database) -> tuple[Project, Project, list[str]]:
    """North (group, 2 packages) and 南区车道 (team, 3 packages of 2 tasks each).

    In 南区车道: #1 #2 held by wang untouched; #3 #4 saved and submitted by li and in review
    by zhao; #5 #6 unassigned. Returns the south task ids in list order.
    """
    north, _ = production_fixture(db, "group", count=4, package_size=2)
    south, _ = production_fixture(db, "team", count=6, package_size=2)
    north, south = _named(db, north, NORTH), _named(db, south, SOUTH)
    tasks = [task.id for task in list_tasks(db, south.id)]
    run = ServiceRunner(db)
    run("manage_users", {"operation": "create", "user_id": "boss", "display_name": "老板"})
    for user, name, role in PEOPLE:
        run("manage_users", {"operation": "create", "user_id": user, "display_name": name}, "boss")
        binding = {"operation": "bind_role", "user_id": user, "role_id": role}
        run("manage_users", {**binding, "project_id": south.id}, "boss")
        run("manage_users", {**binding, "project_id": north.id}, "boss")
    run("assign_tasks", {"task_ids": tasks[0:2], "actor": "wang"}, "boss")
    run("assign_tasks", {"task_ids": tasks[2:4], "actor": "li"}, "boss")
    for task in tasks[2:4]:
        save(db, task, "li")
        submit(db, task, "li")
    run("assign_tasks", {"task_ids": tasks[2:4], "actor": "zhao", "stage": "review"}, "boss")
    return north, south, tasks


def planned(
    db: Database,
    text: str,
    answers: list[dict[str, object]],
    context: PageContext,
    actor: str = "boss",
) -> IntentResult:
    """Plan through recorded model answers in order."""
    sent: list[ModelRequest] = []

    def complete(request: ModelRequest) -> ModelResponse:
        sent.append(request)
        return ModelResponse(content=json.dumps(answers[min(len(sent), len(answers)) - 1]))

    turn = PlannerTurn(text=text, actor=actor, context=context)
    result = plan_turn(db, turn, complete=complete, access=ModelAccess(model="m", allowed=True))
    assert result is not None
    return result


def steps(*items: tuple[str, dict[str, object]], kind: str = "plan") -> dict[str, object]:
    """A model plan with one step per (action, params)."""
    listed = [
        {"id": f"s{index}", "action": action, "params": params}
        for index, (action, params) in enumerate(items, start=1)
    ]
    return {"kind": kind, "steps": listed}


def targets(result: IntentResult, position: int = 0) -> list[str]:
    """Task ids one planned step acts on, listed or fanned out."""
    assert result.kind == "plan", result.text
    assert result.chain is not None
    step = result.chain.steps[position]
    listed = step.params.get("task_ids")
    if isinstance(listed, list):
        return [str(item) for item in listed]
    single = step.params.get("task_id")
    return [str(single)] if single else [str(item.get("task_id")) for item in step.items]


def shown(result: IntentResult, position: int = 0) -> dict[str, str]:
    """Card lines of one planned step, label to value."""
    assert result.chain is not None
    return {detail.label: detail.value for detail in result.chain.steps[position].details}
