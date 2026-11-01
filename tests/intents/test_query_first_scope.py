# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Described groups are read before planning and every plan passes fixed checks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ModelResponse,
    ScriptedResponse,
)
from datakeel.core.errors import ProviderError, ValidationError
from datakeel.core.intent_models import ActionChain, ChainStep, IntentResult, PageContext
from datakeel.intents import turns
from datakeel.intents.chains import resolve_refs
from datakeel.intents.model_parse import AGENT_NAME
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.intents.recipes import match_recipe
from datakeel.intents.task_scope import select_tasks
from datakeel.ontology.models import ObjectSet
from datakeel.storage.intent_reads import TaskSnapshot
from datakeel.storage.object_queries import evaluate
from datakeel.storage.production_queries import get_task, list_tasks
from tests.intents.support import images
from tests.production_helpers import production_fixture
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database

PEOPLE = (
    ("wang", "小王", "annotator"),
    ("li", "小李", "annotator"),
    ("zhao", "小赵", "reviewer"),
    ("chen", "小陈", "annotator"),
)


def world(db: Database) -> tuple[Project, list[str]]:
    """Six tasks in list order, and chen's account disabled.

    #1 #2 held by wang untouched, #3 held by li with a saved annotation, #4 submitted and in
    review by zhao, #5 #6 unassigned.
    """
    project, _ = production_fixture(db, "team", count=6, package_size=3)
    tasks = [task.id for task in list_tasks(db, project.id)]
    run = ServiceRunner(db)
    run("manage_users", {"operation": "create", "user_id": "boss", "display_name": "老板"})
    for user, name, role in PEOPLE:
        run("manage_users", {"operation": "create", "user_id": user, "display_name": name}, "boss")
        binding = {"operation": "bind_role", "user_id": user, "role_id": role}
        run("manage_users", {**binding, "project_id": project.id}, "boss")
    run("assign_tasks", {"task_ids": tasks[0:2], "actor": "wang"}, "boss")
    run("assign_tasks", {"task_ids": tasks[2:4], "actor": "li"}, "boss")
    save(db, tasks[2], "li")
    save(db, tasks[3], "li")
    submit(db, tasks[3], "li")
    run("assign_tasks", {"task_ids": [tasks[3]], "actor": "zhao", "stage": "review"}, "boss")
    run("manage_users", {"operation": "update", "user_id": "chen", "status": "disabled"}, "boss")
    return project, tasks


def planned(
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


def step(action: str, params: dict[str, object]) -> dict[str, object]:
    """A one-step model plan."""
    return {"kind": "plan", "steps": [{"id": "s1", "action": action, "params": params}]}


def tasks_of(result: IntentResult) -> list[str]:
    """Task ids a plan's first step acts on, whether listed or fanned out."""
    assert result.kind == "plan", result.text
    assert result.chain is not None
    first = result.chain.steps[0]
    listed = first.params.get("task_ids")
    if isinstance(listed, list):
        return [str(item) for item in listed]
    single = first.params.get("task_id")
    return [str(single)] if single else [str(item["task_id"]) for item in first.items]


def test_a_described_group_is_read_first_and_protected_tasks_are_left_out(db: Database) -> None:
    """全部 leaves out held and annotated tasks and says so; 没人领 means unassigned."""
    project, tasks = world(db)
    page = PageContext(project_id=project.id)
    everything = step("assign_tasks", {"task_ids": {"$tasks": {}}, "actor": "小李"})
    result, _ = planned(db, "把所有任务派给小李", [everything], page)
    assert tasks_of(result) == tasks[4:6]
    assert result.chain is not None
    shown = {detail.label: detail.value for detail in result.chain.steps[0].details}
    assert "3 条在别人手上" in shown.get("已排除", "")
    nobody = step("assign_tasks", {"task_ids": {"$tasks": {"holder": "nobody"}}, "actor": "li"})
    result, _ = planned(db, "把没人领的任务派给小李", [nobody], page)
    assert tasks_of(result) == tasks[4:6]
    numbered = step("assign_tasks", {"task_ids": ["#5"], "actor": "wang"})
    result, _ = planned(db, "Assign task #5 to Wang", [numbered], page)
    assert tasks_of(result) == [tasks[4]]
    wrapped = step("assign_tasks", {"task_ids": [{"$tasks": {"numbers": [5, 6]}}], "actor": "li"})
    result, _ = planned(db, "Assign tasks #5 and #6 to Li", [wrapped], page)
    assert tasks_of(result) == tasks[4:6]
    bare, _ = planned(db, "把任务派给小李", [everything], page)
    assert bare.kind == "clarify"
    assert "全部" in bare.text


def test_saved_annotation_is_protected_unless_the_words_include_it(db: Database) -> None:
    """Li's annotated task stays unless 已经标了的也收; a rework count unlocks it too."""
    project, tasks = world(db)
    page = PageContext(project_id=project.id)
    held = {"$tasks": {"holder": "小李"}}
    plain = step("revoke_assignment", {"task_id": held})
    kept, _ = planned(db, "把小李手上的任务收回来", [plain], page, actor="boss")
    assert kept.kind == "clarify"
    assert "已有人工标注" in kept.text
    included = {"$tasks": {"holder": "小李", "include": ["annotated"]}}
    taken, _ = planned(
        db,
        "把小李手上的任务收回来, 已经标了的也收",
        [step("revoke_assignment", {"task_id": included})],
        page,
    )
    assert tasks_of(taken) == [tasks[2]]


def test_a_disabled_account_is_named_and_never_offered(db: Database) -> None:
    """Work for a disabled person becomes a question that says why and offers others."""
    project, _ = world(db)
    payload = step("assign_tasks", {"task_ids": {"$tasks": {"holder": "nobody"}}, "actor": "小陈"})
    result, _ = planned(db, "把没人领的任务派给小陈", [payload], PageContext(project_id=project.id))
    assert result.kind == "clarify"
    assert "停用" in result.text
    assert result.clarification is not None
    offered = {candidate.id for candidate in result.clarification.candidates}
    assert offered
    assert "chen" not in offered


def test_a_plan_that_changes_nothing_is_answered_instead_of_shown(db: Database) -> None:
    """An existing label, the current lease or an active account: already so, no card."""
    project, _ = world(db)
    page = PageContext(project_id=project.id, label_set_id=project.label_set_id)
    labels = step("create_label_set", {"label_set_id": project.label_set_id, "add_labels": ["Cat"]})
    same, _ = planned(db, "给这个标签集加一个 Cat 标签", [labels], page)
    assert same.kind == "answer", same.text
    assert "已经是这样了" in same.text
    lease = step("configure_project", {"project_id": project.id, "lease_minutes": 10})
    unchanged, _ = planned(db, "把这个项目的领取时限设成 10 分钟", [lease], page)
    assert unchanged.kind == "answer"
    active = step("manage_users", {"operation": "update", "user_id": "小赵", "status": "active"})
    enabled, _ = planned(db, "启用小赵的账号", [active], PageContext())
    assert enabled.kind == "answer"
    changed = step("configure_project", {"project_id": project.id, "lease_minutes": 30})
    planned_change, _ = planned(db, "把这个项目的领取时限设成 30 分钟", [changed], page)
    assert planned_change.kind == "plan"


def test_a_reviewer_s_send_back_is_a_review_decision(db: Database) -> None:
    """打回 on a task in review is repaired once to review_task on its latest revision."""
    _, tasks = world(db)
    page = PageContext(task_id=tasks[3])
    reopen = step("reopen_task", {"task_id": tasks[3], "reason": "打回"})
    decision = step("review_task", {"task_id": tasks[3], "decision": "rework"})
    result, sent = planned(db, "这条打回", [reopen, decision], page, actor="zhao")
    assert len(sent) == 2
    assert "review_task" in sent[1].messages[-1].content
    assert result.kind == "plan", result.text
    assert result.chain is not None
    params = result.chain.steps[0].params
    assert params["decision"] == "rework"
    assert params["revision_id"] == get_task(db, tasks[3]).latest_revision_id
    stuck, _ = planned(db, "这条打回", [reopen, reopen], page, actor="zhao")
    assert stuck.kind == "clarify"
    assert "打回" in stuck.text


def test_a_model_step_needs_words_that_ask_for_a_model(db: Database) -> None:
    """A plain label set is never drafted by a cloud model the person did not ask for."""
    world(db)
    drafted = step("draft_label_set", {"name": "行人", "topic": "行人"})
    created = step("create_label_set", {"name": "行人", "labels": ["行人"]})
    text = "建一个行人标签集, 标签就一个行人"
    result, sent = planned(db, text, [drafted, created], PageContext())
    assert len(sent) == 2
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert [item.action for item in result.chain.steps] == ["create_label_set"]
    asked, _ = planned(db, text, [drafted, drafted], PageContext())
    assert asked.kind == "clarify"
    assert "模型" in asked.text
    draft_words, _ = planned(db, "参考这些图起草一份行人标签集", [drafted], PageContext())
    assert draft_words.kind != "clarify" or "模型" not in draft_words.text


def test_failed_model_calls_are_reported_as_failures_with_the_reason(db: Database) -> None:
    """A timeout or an HTTP status is said as a failed model call, never as unsupported."""
    project, _ = world(db)
    page = PageContext(project_id=project.id)
    for error, said in (
        (ProviderError("timeout"), "超时"),
        (ProviderError("http_429", status_code=429), "HTTP 429"),
    ):

        def broken(_request: ModelRequest, error: ProviderError = error) -> ModelResponse:
            raise error

        turn = PlannerTurn(text="每包 3 张重新切包", actor="boss", context=page)
        access = ModelAccess(model="m", allowed=True)
        result = plan_turn(db, turn, complete=broken, access=access)
        assert result is not None
        assert result.kind == "failed"
        assert "模型调用失败" in result.text
        assert said in result.text


def test_a_missing_feature_is_said_and_only_a_real_choice_is_asked(db: Database) -> None:
    """kind=none says the platform lacks it, naming close actions; only "choose" asks (10.6)."""
    world(db)
    related: dict[str, object] = {
        "kind": "none",
        "reason": "email",
        "related": ["export_dataset", "made_up"],
    }
    missing, _ = planned(db, "把街景图发邮件给客户", [related], PageContext())
    assert missing.kind == "unsupported"
    assert missing.clarification is None
    assert "平台没有这个功能" in missing.text
    assert "导出" in missing.text
    english, _ = planned(db, "Email the street images to the client", [related], PageContext())
    assert english.kind == "unsupported"
    assert "no feature" in english.text
    unrelated: dict[str, object] = {"kind": "none", "reason": "travel", "related": []}
    travel, _ = planned(db, "帮我订一张去北京的高铁票", [unrelated], PageContext())
    assert travel.kind == "unsupported"
    either: dict[str, object] = {
        "kind": "none",
        "reason": "two fit",
        "choose": ["revoke_assignment", "release_task"],
    }
    asked, _ = planned(db, "把这条还回去", [either], PageContext())
    assert asked.kind == "clarify"
    assert asked.clarification is not None
    assert [item.id for item in asked.clarification.candidates] == [
        "revoke_assignment",
        "release_task",
    ]


def test_rejected_values_are_named_without_the_raw_validator_text(db: Database) -> None:
    """A value out of range is asked about by its field name and range, in plain words."""
    project, _ = world(db)
    payload = step("configure_project", {"project_id": project.id, "lease_minutes": 5000})
    result, _ = planned(
        db, "把这个项目的领取时限设成 5000 分钟", [payload], PageContext(project_id=project.id)
    )
    assert result.kind == "clarify"
    assert "领取时限" in result.text
    assert "1440" in result.text
    assert "Input should" not in result.text


def test_a_later_step_can_take_one_package_an_earlier_split_made() -> None:
    """{"$ref": "s1.package_ids", "$nth": 2} is the second package the split produced."""
    split = ChainStep(
        id="s1",
        action="split_packages",
        status="succeeded",
        outputs={"package_ids": ["p1", "p2"]},
    )
    chain = ActionChain(steps=[split])
    assert resolve_refs({"$ref": "s1.package_ids", "$nth": 2}, chain) == "p2"
    assert resolve_refs({"$ref": "s1.package_ids"}, chain) == ["p1", "p2"]
    try:
        resolve_refs({"$ref": "s1.package_ids", "$nth": 3}, chain)
    except ValidationError:
        missing = True
    else:
        missing = False
    assert missing


def test_the_planner_sees_every_parameter_and_asks_for_steady_json(db: Database) -> None:
    """Signatures name each action's parameters; the request asks for JSON at temperature 0."""
    project, _ = world(db)
    payload = step("split_packages", {"project_id": project.id, "package_size": 3})
    _, sent = planned(db, "每包 3 张重新切包", [payload], PageContext(project_id=project.id))
    stable = sent[0].messages[0].content
    assert "status=active|disabled" in stable
    assert "review_task(task_id*, revision_id*, decision*=approve|rework" in stable
    assert sent[0].temperature == 0
    assert sent[0].json_output
    volatile = sent[0].messages[1].content
    assert "status=disabled" in volatile
    assert "domain=" not in volatile or "annotation_type=" in volatile


def test_internal_errors_are_said_plainly_without_the_raw_text(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An internal error while planning ends as a failed turn with a plain sentence."""

    def broken(*_args: object, **_kwargs: object) -> None:
        message = "secret internal detail"
        raise ValidationError(message)

    monkeypatch.setattr(turns, "plan_turn", broken)
    conversation = create_conversation(db, ConversationCreate())
    script = [ScriptedResponse(agent=AGENT_NAME, content='{"kind": "none"}')]
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="每包 3 张重新切包", context=PageContext()),
            provider=FakeProvider(script),
        )
    )
    intent = next(event.intent for event in events if event.intent is not None)
    assert intent.kind == "failed"
    assert "secret" not in intent.text
    assert "内部出错" in intent.text


def test_unassigned_means_nobody_holds_it_and_it_is_still_open() -> None:
    """Without any protection, holder=nobody still keeps only open, unheld tasks."""
    snapshots = [
        TaskSnapshot(
            id="a",
            number=1,
            state="in_progress",
            round=0,
            package_id="p",
            annotated=False,
            holder="wang",
            stage="annotation",
        ),
        TaskSnapshot(id="b", number=2, state="submitted", round=0, package_id="p", annotated=True),
        TaskSnapshot(id="c", number=3, state="pending", round=0, package_id="p", annotated=False),
    ]
    found = select_tasks(snapshots, {"holder": "nobody"}, action="reopen_task", speaker="boss")
    assert found.ids == ["c"]
    numbered = select_tasks(snapshots, {"numbers": [2]}, action="assign_tasks", speaker="boss")
    # A named task already handed in cannot be assigned; it is left out and said.
    assert numbered.ids == []
    assert numbered.excluded == {"closed": 1}
    named = select_tasks(snapshots, {"numbers": [2]}, action="reopen_task", speaker="boss")
    assert named.ids == ["b"]
    assert select_tasks(snapshots, {"numbers": [9]}, action="assign_tasks", speaker="boss").missing


def test_a_for_phrase_that_names_the_data_is_not_a_label() -> None:
    """A "for" phrase naming the street images is the data; the label is the traffic light."""
    text = "Create a traffic light box annotation project for these street images"
    draft = match_recipe(text)
    assert draft is not None
    labels = draft.steps[0].params["labels"]
    assert isinstance(labels, list)
    assert [item["name"] for item in labels if isinstance(item, dict)] == ["traffic light"]


def test_a_full_skill_list_never_drops_skills_the_person_did_not_mention(db: Database) -> None:
    """Adding a skill as skill_ids would wipe Li's others: repaired once to add_skill_ids."""
    world(db)
    run = ServiceRunner(db)
    for skill, name in (("box", "车辆框"), ("classify", "图片分类")):
        skill_params = {"operation": "create", "skill_id": skill, "name": name}
        run("manage_skills", {**skill_params, "annotation_type": "box", "domain": "交通"}, "boss")
    run("manage_users", {"operation": "update", "user_id": "li", "skill_ids": ["box"]}, "boss")
    replaced = step(
        "manage_users", {"operation": "update", "user_id": "li", "skill_ids": ["classify"]}
    )
    added = step(
        "manage_users", {"operation": "update", "user_id": "li", "add_skill_ids": ["classify"]}
    )
    result, sent = planned(db, "Add the 图片分类 skill to Li", [replaced, added], PageContext())
    assert len(sent) == 2
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["skill_ids"] == ["box", "classify"]
    asked, _ = planned(db, "Add the 图片分类 skill to Li", [replaced, replaced], PageContext())
    assert asked.kind == "clarify"
    assert "车辆框" in asked.text or "box" in asked.text


def test_a_missing_choice_is_asked_with_its_allowed_values(db: Database) -> None:
    """A review decision left out is asked about with approve and rework to pick from."""
    _, tasks = world(db)
    undecided = step("review_task", {"task_id": tasks[3]})
    result, _ = planned(db, "看下这条", [undecided], PageContext(task_id=tasks[3]), actor="zhao")
    assert result.kind == "clarify"
    assert result.clarification is not None
    assert [item.id for item in result.clarification.candidates] == ["approve", "rework"]


def test_a_role_is_bound_not_written_into_an_account_update(db: Database) -> None:
    """Roles written into an account update change nothing: repaired once to bind_role."""
    project, _ = world(db)
    wrong = step(
        "manage_users", {"operation": "update", "user_id": "wang", "role_ids": ["reviewer"]}
    )
    bind = {"operation": "bind_role", "user_id": "wang", "role_id": "reviewer"}
    right = step("manage_users", {**bind, "project_id": project.id})
    context = PageContext(project_id=project.id)
    text = "给小王加上审核员角色, 在这个项目里"
    result, sent = planned(db, text, [wrong, right], context)
    assert len(sent) == 2
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["operation"] == "bind_role"
    asked, _ = planned(db, text, [wrong, wrong], context)
    assert asked.kind == "clarify"


def test_files_named_by_file_name_resolve_to_exactly_those(db: Database, tmp_path: Path) -> None:
    """A file the person names is that one file; a name not in the dataset is asked about."""
    dataset = images(db, tmp_path / "images")
    whole = evaluate(db, ObjectSet(dataset_id=dataset.id, limit=100))
    target = whole.objects[1]
    name = str(target.properties["filename"])
    context = PageContext(dataset_id=dataset.id)
    named = {"$files": {"kind": "named", "names": [name]}}
    result, _ = planned(
        db, f"把 {name} 隔离", [step("quarantine_files", {"selection": named})], context
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    selection = result.chain.steps[0].params["selection"]
    assert isinstance(selection, dict)
    assert selection["filters"][0]["value"] == [target.asset_ref.asset_id]  # type: ignore[index,call-overload]
    unknown = {"$files": {"kind": "named", "names": ["nope.png"]}}
    asked, _ = planned(
        db, "把 nope.png 隔离", [step("quarantine_files", {"selection": unknown})], context
    )
    assert asked.kind == "clarify"


def test_structured_values_on_the_card_read_as_names_not_keys_or_ids(
    db: Database, tmp_path: Path
) -> None:
    """Metadata and definitions show plain field names, and a known identity shows its name."""
    dataset = images(db, tmp_path / "images")
    context = PageContext(dataset_id=dataset.id)
    values: dict[str, object] = {
        "dataset_id": dataset.id,
        "values": {"采集城市": "杭州"},
        "reason": "补录",
    }
    text = "给这个数据集记一条元数据: 采集城市是杭州, 原因是补录"
    result, _ = planned(db, text, [step("save_metadata", values)], context)
    assert result.chain is not None, result.text
    shown = {detail.label: detail.value for detail in result.chain.steps[0].details}
    assert shown.get("元数据") == "采集城市: 杭州"
    target = {"asset_id": dataset.id}
    definition: dict[str, object] = {
        "definition": {"target": target, "name": "街景", "owner": "data-team"}
    }
    card, _ = planned(
        db, "把这个数据集做成数据资产", [step("create_data_asset", definition)], context
    )
    assert card.chain is not None, card.text
    (line,) = [item.value for item in card.chain.steps[0].details if item.label == "定义"]
    assert dataset.name in line
    assert dataset.id not in line


def test_an_answer_naming_no_registered_read_still_gets_an_answer(db: Database) -> None:
    """A model answer whose read is not registered ends as unsupported, never in silence."""
    project, _ = world(db)
    invented = {"kind": "answer", "steps": [{"id": "s1", "action": "read nothing", "params": {}}]}
    result, _ = planned(db, "看看有没有泄漏", [invented], PageContext(project_id=project.id))
    assert result.kind == "unsupported"


def test_upgrading_to_the_tier_the_project_has_is_already_so(db: Database) -> None:
    """The project is already on the team tier: answered, no card."""
    project, _ = world(db)
    same = step("upgrade_project", {"project_id": project.id, "workflow_tier": "team"})
    result, _ = planned(db, "把这个项目升到团队档", [same], PageContext(project_id=project.id))
    assert result.kind == "answer", result.text
    assert result.chain is None
