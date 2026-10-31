# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX4: the look-up-first planner reads before it proposes, and only reads."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.catalog import build_catalog
from datakeel.intents.explore import EXPLORE_LIMIT, LAST_LOOK, Lookups
from datakeel.intents.model_parse import INSTRUCTIONS
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.production_queries import get_task
from tests.intents.fix3_support import SOUTH, steps, targets, two_projects

if TYPE_CHECKING:
    from collections.abc import Sequence

    from datakeel.core.agent_models import ModelRequest, ModelResponse
    from datakeel.core.intent_models import IntentResult
    from datakeel.storage.database import Database


def explored_plan(
    db: Database, text: str, answers: Sequence[object], actor: str = "boss"
) -> tuple[list[ModelRequest], IntentResult]:
    """Plan with look-ups through recorded model answers in order (the last one repeats)."""
    from datakeel.core.agent_models import ModelResponse  # noqa: PLC0415

    sent: list[ModelRequest] = []

    def complete(request: ModelRequest) -> ModelResponse:
        sent.append(request)
        return ModelResponse(content=json.dumps(answers[min(len(sent), len(answers)) - 1]))

    turn = PlannerTurn(text=text, actor=actor, context=PageContext())
    access = ModelAccess(model="m", allowed=True, explore=True)
    result = plan_turn(db, turn, complete=complete, access=access)
    assert result is not None
    return sent, result


def test_look_ups_are_answered_and_the_plan_goes_through_the_usual_checks(db: Database) -> None:
    """Objects, a read and registry entries come back to the model; the plan is checked."""
    _, south, tasks = two_projects(db)
    answers = [
        {"look": "objects", "kind": "user", "words": "小王"},
        {
            "look": "read",
            "action": "production_objects",
            "params": {"kind": "production_task", "project_id": south.id},
        },
        {"look": "entries", "words": "assign tasks to a person"},
        steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "wang"})),
    ]
    sent, result = explored_plan(db, f"{SOUTH}没人领的两条给小王", answers)
    assert len(sent) == len(answers)
    first = sent[0].messages
    # The plan instructions stay; the registry and the catalog are looked up, not listed.
    assert first[0].content.startswith(INSTRUCTIONS)
    assert "Registry:" not in first[0].content
    assert "Catalog:" not in first[1].content
    assert "Speaker id: boss" in first[1].content
    found = [request.messages[-1].content for request in sent[1:]]
    assert "wang" in found[0]
    assert "小王" in found[0]
    assert tasks[4] in found[1]
    assert "assign_tasks(" in found[2]
    assert result.kind == "plan", result.text
    assert targets(result) == tasks[4:6]
    # Proposed only: nothing is assigned until a person confirms.
    assert get_task(db, tasks[4]).annotator_id is None


def test_a_write_named_as_a_look_up_is_never_run(db: Database) -> None:
    """Only registered reads run as look-ups; an action named there is refused, not run."""
    _, _, tasks = two_projects(db)
    write = {"task_ids": tasks[4:6], "actor": "wang"}
    answers: list[dict[str, object]] = [
        {"look": "read", "action": "assign_tasks", "params": write},
        {"kind": "none", "reason": "nothing fits", "related": []},
    ]
    sent, result = explored_plan(db, "把剩下的给小王", answers)
    assert len(sent) == len(answers)
    assert "not a registered read" in sent[1].messages[-1].content
    assert result.kind == "unsupported"
    assert get_task(db, tasks[4]).annotator_id is None


def test_look_ups_stop_at_the_limit_and_the_last_answer_is_read_as_the_plan(
    db: Database,
) -> None:
    """The last allowed look-up says so; a model that keeps looking is stopped."""
    _, _, tasks = two_projects(db)
    answers = [{"look": "entries", "words": "assign"}] * EXPLORE_LIMIT + [
        steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "wang"}))
    ]
    sent, result = explored_plan(db, f"{SOUTH}没人领的两条给小王", answers)
    assert len(sent) == EXPLORE_LIMIT + 1
    assert sent[EXPLORE_LIMIT].messages[-1].content.endswith(LAST_LOOK)
    assert LAST_LOOK not in sent[EXPLORE_LIMIT - 1].messages[-1].content
    assert result.kind == "plan", result.text
    endless, given_up = explored_plan(db, f"{SOUTH}没人领的两条给小王", answers[:1])
    # A model that keeps looking things up is stopped; its last reply plans nothing.
    assert len(endless) == EXPLORE_LIMIT + 1
    assert given_up.kind == "unsupported"


def test_look_up_results_are_bounded_plain_data(db: Database) -> None:
    """Unknown look-ups, kinds, words and failed reads each get a plain answer."""
    _, south, _ = two_projects(db)
    lookups = Lookups(db, build_catalog(db, south.id), ToolCallContext(actor="boss"))
    assert "Unknown look-up" in lookups.found({"look": "files"})
    assert lookups.found({"look": "objects", "kind": "widget", "words": ""}) == "No widget objects."
    everyone = lookups.found({"look": "objects", "kind": "user", "words": "nobody here"})
    assert "wang" in everyone
    assert "zhao" in everyone
    only = lookups.found({"look": "objects", "kind": "user", "words": "小李"})
    assert "li" in only
    assert "wang" not in only
    failed = lookups.found({"look": "read", "action": "annotator_workload", "params": []})
    assert failed.startswith("The read failed")
    workload = lookups.found(
        {"look": "read", "action": "annotator_workload", "params": {"project_id": south.id}}
    )
    assert "wang" in workload
