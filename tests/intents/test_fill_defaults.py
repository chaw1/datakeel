# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Values the person implied but the model left out, and plain answers for workload reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.answers import answer_text
from datakeel.intents.model_parse import parse_response
from datakeel.intents.recipes import match_recipe
from tests.intents.support import model_plan, team

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database


def test_revocation_keeps_the_persons_words_as_its_reason(db: Database) -> None:
    """A model plan without a reason records the request itself instead of asking for one."""
    project, _ = team(db)
    text = "Take the untouched tasks away from Xiao Wang and give them to Xiao Li"
    assert match_recipe(text) is None
    held = {"$tasks": {"holder": "Xiao Wang", "untouched": True}}
    revoke: dict[str, object] = {"task_id": held}
    assign: dict[str, object] = {"task_ids": held, "actor": "Xiao Li", "strategy": "assign"}
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [
            {"id": "s1", "action": "revoke_assignment", "params": revoke},
            {"id": "s2", "action": "assign_tasks", "params": assign},
        ],
    }
    result = model_plan(db, text, payload, PageContext(project_id=project.id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["reason"] == text


def test_unnamed_label_set_and_project_take_the_label_names(db: Database) -> None:
    """Neither name was given: both become the spoken labels instead of a question."""
    project, _ = team(db)
    labels = [{"id": "road", "name": "road"}, {"id": "sidewalk", "name": "sidewalk"}]
    created: dict[str, object] = {
        "label_set_id": {"$ref": "s1.label_set_id"},
        "label_set_version": {"$ref": "s1.label_set_version"},
    }
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [
            {"id": "s1", "action": "create_label_set", "params": {"labels": labels}},
            {"id": "s2", "action": "create_project", "params": created},
        ],
    }
    text = "Outline road and sidewalk on these images, then open the project"
    result = model_plan(db, text, payload, PageContext(dataset_id=project.dataset_id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    names = [step.params.get("name") for step in result.chain.steps]
    assert names[0] == "road, sidewalk"
    assert names[1] == "road, sidewalk"


def test_workload_question_is_answered_with_held_and_finished_counts() -> None:
    """Workload is not phrased as a rework rate."""
    data: JsonValue = {
        "annotators": [
            {"actor": "li", "assigned": 1, "completed": 1, "review_count": 0},
            {"actor": "wang", "assigned": 2, "completed": 0, "review_count": 0},
        ]
    }
    assert (
        answer_text("annotator_workload", data, "zh")
        == "每人分到/已完成的任务数: wang 2/0, li 1/1。"
    )
    assert "rework" not in answer_text("annotator_workload", data, "en")


def test_read_prefix_copied_from_the_registry_is_dropped() -> None:
    """A model writing read_next_task still names the registered read function."""
    content = '{"kind": "answer", "steps": [{"action": "read_next_task", "params": {}}]}'
    draft = parse_response(content, "zh")
    assert [step.action for step in draft.steps] == ["next_task"]


def test_draft_without_a_name_is_named_after_its_topic(db: Database) -> None:
    """The topic the person gave names the drafted label set instead of a question."""
    project, _ = team(db)
    params: dict[str, object] = {"topic": "animals", "dataset_id": project.dataset_id}
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [{"id": "s1", "action": "draft_label_set", "params": params}],
    }
    text = "Using these images, come up with categories for animals"
    result = model_plan(db, text, payload, PageContext(dataset_id=project.dataset_id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["name"] == "animals"


def test_redundant_page_project_is_ignored_and_task_plurals_renamed(db: Database) -> None:
    """A project_id repeating the page and task_ids on a single-task action still plan."""
    project, tasks = team(db)
    held = {"$tasks": {"holder": "小王", "untouched": True}}
    revoke: dict[str, object] = {"task_ids": held, "reason": "转给小赵"}
    assign: dict[str, object] = {"task_ids": held, "actor": "小赵", "project_id": project.id}
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [
            {"id": "s1", "action": "revoke_assignment", "params": revoke},
            {"id": "s2", "action": "assign_tasks", "params": assign},
        ],
    }
    text = "把这个项目里小王还没开工的任务收回来, 转给小赵"
    result = model_plan(db, text, payload, PageContext(project_id=project.id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    (revoke_step,) = result.chain.steps
    assert sorted(str(item["task_id"]) for item in revoke_step.items) == sorted(
        [tasks[0].id, tasks[1].id]
    )
    assert "上一步完成后再规划" in result.text


def test_several_reads_without_a_write_answer_the_first(db: Database) -> None:
    """A plan made only of reads is answered, never stored as an empty chain."""
    project, _ = team(db)
    reads = [
        {"id": "s1", "action": "project_progress", "params": {"project_id": project.id}},
        {"id": "s2", "action": "annotator_workload", "params": {"project_id": project.id}},
    ]
    payload: dict[str, object] = {"kind": "plan", "steps": reads}
    result = model_plan(db, "进度和工作量", payload, PageContext(project_id=project.id))
    assert result.kind == "answer"
    assert result.answer is not None
    assert result.answer.function == "project_progress"
