# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3 P5-P7: new or existing, scope-less reads, and every part of a request accounted for."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from datakeel.core.intent_models import PageContext
from datakeel.label_drafts.model import model_draft
from datakeel.label_drafts.models import CategorySource, DraftInputs, SampleSource
from tests.intents.fix3_support import SOUTH, planned, shown, steps, targets, two_projects
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def _skills(db: Database) -> None:
    run = ServiceRunner(db)
    skill = {"operation": "create", "skill_id": "box", "name": "框选"}
    run("manage_skills", {**skill, "annotation_type": "box", "domain": "traffic"}, "boss")
    for user in ("wang", "li"):
        run("manage_users", {"operation": "update", "user_id": user, "skill_ids": ["box"]}, "boss")


def test_a_new_name_that_exists_is_said_and_never_planned_as_a_copy(db: Database) -> None:
    """Every creating action, with or without 新建, single or in a chain, zh and en."""
    north, _, _ = two_projects(db)
    _skills(db)
    page = PageContext(project_id=north.id)
    project = {
        "name": SOUTH,
        "dataset_id": "x",
        "version_id": "x",
        "label_set_id": north.label_set_id,
    }
    taken = planned(db, f"新建一个项目叫{SOUTH}", [steps(("create_project", project))], page)
    assert taken.kind == "clarify", taken.text
    assert f"已经有一个叫「{SOUTH}」的项目" in taken.text
    assert taken.clarification is not None
    assert taken.clarification.fields == []
    for action, params, said in (
        ("manage_skills", {"operation": "create", "skill_id": "box", "name": "Box"}, "box skill"),
        ("define_role", {"role_id": "annotator", "name": "annotator"}, "annotator"),
        ("manage_users", {"operation": "create", "user_id": "wang", "display_name": "王"}, "wang"),
    ):
        result = planned(db, f"Create a new {said}", [steps((action, params))], page)
        assert result.kind == "clarify", (action, result.text)
        assert "already a" in result.text, result.text
    chain = steps(
        ("manage_users", {"operation": "create", "user_id": "newbie", "display_name": "新人"}),
        ("manage_skills", {"operation": "create", "skill_id": "box", "name": "框选"}),
    )
    both = planned(db, "加一个新人账号, 再建一个框选技能", [chain], page)
    assert both.kind == "clarify"
    assert "已经有一个叫「框选」的技能" in both.text
    fresh = steps(
        ("manage_users", {"operation": "create", "user_id": "newbie", "display_name": "新人"})
    )
    created = planned(db, "加一个新人账号 newbie", [fresh], page)
    assert created.kind == "plan", created.text


def test_a_skill_edit_card_says_how_many_people_hold_it(db: Database) -> None:
    """Renaming or retiring a skill shows its current holders on the card."""
    two_projects(db)
    _skills(db)
    rename = steps(("manage_skills", {"operation": "update", "skill_id": "box", "name": "画框"}))
    result = planned(db, "把框选技能改名叫画框", [rename], PageContext())
    assert result.kind == "plan", result.text
    assert shown(result).get("目前持有的人") == "2 人"
    english = planned(db, "Rename the box skill to Boxing", [rename], PageContext())
    assert shown(english).get("Held by") == "2 people"


def test_a_read_without_a_project_uses_the_speaker_s_only_one_and_says_so(db: Database) -> None:
    """One project: answered and named; several: asked with those projects to choose from."""
    north, south, _ = two_projects(db)
    run = ServiceRunner(db)
    run("manage_users", {"operation": "create", "user_id": "zhou", "display_name": "小周"}, "boss")
    binding = {"operation": "bind_role", "user_id": "zhou", "role_id": "annotator"}
    run("manage_users", {**binding, "project_id": south.id}, "boss")
    read = steps(("project_progress", {}), kind="answer")
    mine = planned(db, "我这边的进度怎么样了", [read], PageContext(), actor="zhou")
    assert mine.kind == "answer", mine.text
    assert mine.text.startswith(f"按你所在的「{SOUTH}」项目")
    english = planned(db, "How is my project going?", [read], PageContext(), actor="zhou")
    assert english.text.startswith(f'For your project "{SOUTH}"')
    asked = planned(db, "进度怎么样了", [read], PageContext(), actor="wang")
    assert asked.kind == "clarify"
    assert asked.clarification is not None
    assert {item.id for item in asked.clarification.candidates} == {north.id, south.id}


def test_every_part_of_a_request_is_planned_or_said_why_not(db: Database) -> None:
    """A refused part, an unknown part and a model-skipped part are each reported."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    review = ("review_task", {"task_id": tasks[2], "decision": "approve"})
    assign = ("assign_tasks", {"task_ids": tasks[4:6], "actor": "wang"})
    half = planned(db, "第 3 条通过, 再把 5、6 派给小王", [steps(review, assign)], page, "zhao")
    assert half.kind == "plan", half.text
    assert half.chain is not None
    assert [step.action for step in half.chain.steps] == ["review_task"]
    assert "没有做" in half.text
    assert "没有这个权限" in half.text
    assert any("没有做" in note for note in half.chain.notes)
    unknown = planned(
        db,
        "Give #5 and #6 to Wang and email him",
        [steps(assign, ("send_email", {"to": "wang"}))],
        page,
    )
    assert targets(unknown) == tasks[4:6]
    assert "was not done" in unknown.text
    said = "顺便给小王发个消息"
    skipped = {**steps(assign), "skipped": [{"said": said, "reason": "no action"}]}
    told = planned(db, f"把 5、6 派给小王, {said}", [skipped], page)
    assert told.kind == "plan", told.text
    assert f"另外「{said}」没有做" in told.text
    asked = steps(assign, ("project_progress", {"project_id": south.id}))
    both = planned(db, "把 5、6 派给小王, 顺便说下进度", [asked], page)
    assert both.kind == "plan", both.text
    assert "项目进度" in both.text


def test_an_annotation_only_draft_says_its_examples_came_from_existing_annotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cited samples that carry annotations are counted as existing annotations."""
    monkeypatch.setenv("DATAKEEL_DRAFT_VISION_API_KEY", "test-only")
    inputs = DraftInputs(
        name="车辆",
        categories=(CategorySource(key="car", name_zh="轿车", name_en="Car"),),
        samples=(SampleSource(id="s-1", filename="a.png", labels=("car",)),),
    )
    content = {
        "labels": [{"id": "car", "name_zh": "轿车", "name_en": "Car"}],
        "overview_zh": "车辆框。",
        "overview_en": "Vehicle boxes.",
        "rules": [{"label_id": "car", "text_zh": "框整车", "positive": [{"sample_id": "s-1"}]}],
    }
    body = {
        "choices": [{"message": {"content": json.dumps(content)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 400},
    }
    reply = httpx.MockTransport(lambda _request: httpx.Response(200, json=body))
    with httpx.Client(transport=reply) as client:
        outcome = model_draft(inputs, "cloud-vision", 0.05, client)
    overview = outcome.guidelines.overview_zh
    assert "引用已有标注的样本 1 条" in overview
    assert "抽样文件" not in overview
