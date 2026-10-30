# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every sentence ends in a checked plan, a question, a refusal or a plain answer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.intents import selectors
from datakeel.intents.catalog import CANDIDATE_LIMIT, build_catalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.fill import FillState
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.intents.recipes import recipe_covers
from datakeel.intents.validate import check_step
from datakeel.ontology.models import ObjectSet
from datakeel.storage.object_queries import evaluate
from tests.intents.support import SETUP, images, model_plan, team
from tests.production_helpers import production_fixture
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def scripted(
    db: Database,
    text: str,
    answers: list[dict[str, object]],
    context: PageContext,
    actor: str = "boss",
) -> tuple[IntentResult, list[ModelRequest]]:
    """Plan through recorded model answers in order and keep every request sent."""
    sent: list[ModelRequest] = []

    def complete(request: ModelRequest) -> ModelResponse:
        sent.append(request)
        return ModelResponse(content=json.dumps(answers[min(len(sent), len(answers)) - 1]))

    turn = PlannerTurn(text=text, actor=actor, context=context)
    result = plan_turn(db, turn, complete=complete, access=ModelAccess(model="m", allowed=True))
    assert result is not None
    return result, sent


def _plan(
    action: str, params: dict[str, object], said: dict[str, str] | None = None
) -> dict[str, object]:
    step: dict[str, object] = {"id": "s1", "action": action, "params": params}
    if said:
        step["said"] = said
    return {"kind": "plan", "steps": [step]}


def test_rules_take_the_fast_path_only_when_they_use_every_detail(db: Database) -> None:
    """A count of images the recipe cannot use sends the sentence to the model."""
    assert recipe_covers("建红绿灯框标注\uff0c两人交叉、抽 10%")
    assert not recipe_covers(SETUP)
    team(db)
    result, sent = scripted(db, SETUP, [{"kind": "none", "reason": "no fit"}], PageContext())
    assert len(sent) == 1
    assert result.kind == "unsupported"


def test_nothing_registered_fits_gets_a_plain_answer_listing_what_works(db: Database) -> None:
    """The model found no action: the person hears what the platform can do instead."""
    team(db)
    result, _ = scripted(db, "帮我订一张去上海的机票", [{"kind": "none"}], PageContext())
    assert result.kind == "unsupported"
    assert "换个说法" in result.text


def test_the_speaker_s_own_words_ground_a_translated_name(db: Database) -> None:
    """Quoted words from the sentence ground a project whose stored name is in English."""
    project, _ = team(db)
    text = "把那个自动生成的项目每包 20 张切包"
    payload = _plan(
        "split_packages",
        {"project_id": project.id, "package_size": 20},
        {"project_id": "自动生成的项目"},
    )
    result = model_plan(db, text, payload, PageContext())
    assert result.kind == "plan", result.text
    invented = _plan("split_packages", {"project_id": project.id}, {"project_id": "港口项目"})
    asked = model_plan(db, text, invented, PageContext())
    assert asked.kind == "clarify"


def test_me_is_the_speaker_and_positions_follow_the_task_list(db: Database) -> None:
    """我 resolves to whoever speaks; 前两个任务 are the first two the list shows."""
    project, tasks = team(db)
    payload = _plan("assign_tasks", {"task_ids": {"$tasks": {"first": 2}}, "actor": "我"})
    result = model_plan(db, "把前两个任务分给我", payload, PageContext(project_id=project.id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    params = result.chain.steps[0].params
    assert params["actor"] == "boss"
    assert params["task_ids"] == [tasks[0].id, tasks[1].id]
    beyond = _plan("assign_tasks", {"task_ids": {"$tasks": {"positions": [9]}}, "actor": "li"})
    asked = model_plan(db, "把第9个任务分给小李", beyond, PageContext(project_id=project.id))
    assert asked.kind == "clarify"


def test_unknown_parameters_get_one_repair_round_then_a_question(db: Database) -> None:
    """A parameter the action does not take is never dropped silently."""
    project, _ = team(db)
    wrong = _plan("split_packages", {"project_id": project.id, "size_per_pack": 20})
    fixed = _plan("split_packages", {"project_id": project.id, "package_size": 20})
    context = PageContext(project_id=project.id)
    repaired, sent = scripted(db, "每包 20 张切包", [wrong, fixed], context)
    assert len(sent) == 2
    assert repaired.kind == "plan"
    assert repaired.chain is not None
    assert repaired.chain.steps[0].params["package_size"] == 20
    stuck, sent = scripted(db, "每包 20 张切包", [wrong, wrong], context)
    assert len(sent) == 2
    assert stuck.kind == "clarify"
    assert stuck.clarification is not None
    assert "size_per_pack" in stuck.clarification.question


def test_a_write_the_speaker_may_not_do_is_refused_before_any_question(db: Database) -> None:
    """An annotator asking to re-split hears the missing permission, not a project question."""
    team(db)
    payload = _plan("split_packages", {"package_size": 20})
    result, _ = scripted(db, "切成每包 20 张", [payload], PageContext(), actor="wang")
    assert result.kind == "refuse", result.text
    assert result.clarification is None


def test_step_check_still_refuses_a_project_the_speaker_does_not_manage(db: Database) -> None:
    """A project resolved only while filling is checked again with that project's roles."""
    managed, _ = team(db)
    other, _ = production_fixture(db, "group", count=2)
    ServiceRunner(db)(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "li",
            "role_id": "project_manager",
            "project_id": managed.id,
        },
        "boss",
    )
    state = FillState(actor="li", text="切包")
    catalog = build_catalog(db)
    allowed = DraftStep(
        id="s1", action="split_packages", params={"project_id": managed.id, "request_id": "r1"}
    )
    assert check_step(db, allowed, state, catalog, []).step is not None
    foreign = DraftStep(
        id="s1", action="split_packages", params={"project_id": other.id, "request_id": "r2"}
    )
    assert check_step(db, foreign, state, catalog, []).missing_scopes == ["production:manage"]


def test_adding_a_label_keeps_the_existing_labels_and_shows_the_change(db: Database) -> None:
    """The new version starts from the current one; the card lists what is added."""
    project, _ = team(db)
    payload = _plan(
        "create_label_set", {"label_set_id": project.label_set_id, "add_labels": [{"name": "Dog"}]}
    )
    result = model_plan(db, "给 Generated labels 加一个 Dog 标签", payload, PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    (step,) = result.chain.steps
    names = [item["name"] for item in step.params["labels"]]  # type: ignore[index,union-attr]
    assert names == ["Cat", "Dog"]
    assert step.params["previous_version"] == 1
    tones = {detail.tone: detail.value for detail in step.details}
    assert tones["added"] == "Dog"
    assert "影响 0 条标注" in tones["impact"]


def test_a_subset_resolves_to_exact_files_and_never_widens(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Near duplicates become an id list on the card; a whole-dataset plan is asked about."""
    dataset = images(db, tmp_path / "images")
    whole = evaluate(db, ObjectSet(dataset_id=dataset.id, limit=100))
    files = [item.asset_ref.asset_id for item in whole.objects]
    copies: list[str] = files[1:3]

    def found(*_args: object) -> list[str]:
        return copies

    monkeypatch.setattr(selectors, "near_duplicates", found)
    context = PageContext(dataset_id=dataset.id)
    exact = _plan("quarantine_files", {"selection": {"$files": {"kind": "near_duplicates"}}})
    result = model_plan(db, "把重复的图隔离", exact, context)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    selection = result.chain.steps[0].params["selection"]
    assert selection["filters"][0]["value"] == files[1:3]  # type: ignore[index,call-overload]
    assert any(detail.value.startswith("2 个文件") for detail in result.chain.steps[0].details)
    wide = _plan("quarantine_files", {"selection": {"dataset_id": dataset.id}})
    asked = model_plan(db, "把重复的图隔离", wide, context)
    assert asked.kind == "clarify"
    assert asked.clarification is not None
    assert asked.clarification.fields == ["selection"]
    copies = []
    nothing = model_plan(db, "把重复的图隔离", exact, context)
    assert nothing.kind == "answer"
    assert nothing.chain is None


def test_cards_show_names_and_marked_defaults_and_questions_offer_few_choices(
    db: Database,
) -> None:
    """Ids never reach the card or the question; unset options show their default."""
    project, _ = team(db)
    payload = _plan("split_packages", {"project_id": project.id})
    result = model_plan(db, "切包", payload, PageContext(project_id=project.id))
    assert result.chain is not None
    details = result.chain.steps[0].details
    assert any(detail.value == project.name for detail in details)
    assert not any(project.id in detail.value for detail in details)
    assert any(detail.tone == "default" and "100" in detail.value for detail in details)
    catalog = build_catalog(db)
    assert catalog.of("role")
    assert len(candidates(catalog.of("user") * 3)) == CANDIDATE_LIMIT
    nobody = _plan("assign_tasks", {"task_ids": {"$tasks": {"first": 1}}})
    asked = model_plan(db, "把第一个任务分出去", nobody, PageContext(project_id=project.id))
    assert asked.kind == "clarify"
    assert asked.clarification is not None
    assert 0 < len(asked.clarification.candidates) <= CANDIDATE_LIMIT
    assert "id" not in asked.clarification.question.casefold()


def test_a_version_left_out_beside_an_earlier_step_s_id_is_taken_from_that_step(
    db: Database, tmp_path: Path
) -> None:
    """Publishing the label set made in s1 needs s1's version, not a question to the person."""
    dataset = images(db, tmp_path / "images")
    labels: dict[str, object] = {"name": "路口灯", "labels": ["红绿灯"]}
    made = {"$ref": "s1.label_set_id"}
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [
            {"id": "s1", "action": "create_label_set", "params": labels},
            {"id": "s2", "action": "publish_label_set", "params": {"label_set_id": made}},
            {"id": "s3", "action": "create_project", "params": {"label_set_id": made}},
        ],
    }
    result = model_plan(
        db, "给这批路口图建红绿灯框标注", payload, PageContext(dataset_id=dataset.id)
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    publish, project = result.chain.steps[1].params, result.chain.steps[2].params
    assert publish["version"] == {"$ref": "s1.label_set_version"}
    assert project["label_set_version"] == {"$ref": "s1.label_set_version"}
