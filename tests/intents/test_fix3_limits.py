# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3: groups said any way, protected groups asked, and what execution refuses said first."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.core.release_models import ReleaseView
from datakeel.intents.catalog import build_catalog
from datakeel.intents.planner import ModelAccess, PlannerTurn, plan_turn
from datakeel.intents.public_text import allowed_words, leaks
from datakeel.intents.wording import action_title
from tests.intents.fix3_support import NORTH, SOUTH, planned, shown, steps, targets, two_projects
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    import pytest

    from datakeel.core.agent_models import ModelRequest, ModelResponse
    from datakeel.core.intent_models import IntentResult
    from datakeel.storage.database import Database


def test_a_group_left_unwrapped_or_counted_from_the_end_is_that_group(db: Database) -> None:
    """Conditions without their $tasks wrapper, "the last N", alone or with a condition."""
    north, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    bare = {"project": SOUTH, "holder": "nobody", "first": 1}
    result = planned(
        db,
        "把南区车道第一个没人领的任务派给小李",
        [steps(("assign_tasks", {"task_ids": bare, "actor": "li"}))],
        page,
    )
    assert targets(result) == tasks[4:5]
    last = {"$tasks": {"last": 2}}
    result = planned(
        db,
        "把最后两个任务派给小李",
        [steps(("assign_tasks", {"task_ids": last, "actor": "li"}))],
        page,
    )
    assert targets(result) == tasks[4:6]
    assert "2 个任务: #5、#6" in shown(result).values()
    free = {"$tasks": {"holder": "nobody", "last": 1}}
    result = planned(
        db,
        "把没人领的最后一个派给小李",
        [steps(("assign_tasks", {"task_ids": free, "actor": "li"}))],
        page,
    )
    assert targets(result) == tasks[5:6]
    english = {"$tasks": {"project": SOUTH, "last": 1}}
    result = planned(
        db,
        f"Give the last task of {SOUTH} to Li",
        [steps(("assign_tasks", {"task_ids": english, "actor": "li"}))],
        PageContext(project_id=north.id),
    )
    assert targets(result) == tasks[5:6]
    # "最后一条" with nothing else said is the last in the whole list, even when another
    # task is the last one the step could act on.
    back = steps(("revoke_assignment", {"task_ids": {"$tasks": {"last": 1}}}))
    result = planned(db, "把列表最后一条收回来", [back], page)
    assert result.kind == "answer", result.text
    assert "没有人领" in result.text
    ServiceRunner(db)("assign_tasks", {"task_ids": tasks[5:6], "actor": "li"}, "boss")
    place = steps(("assign_tasks", {"task_ids": {"$tasks": {"last": 1}}, "actor": "wang"}))
    assert targets(planned(db, "把最后一个任务派给小王", [place], page)) == tasks[5:6]
    free = steps(
        ("assign_tasks", {"task_ids": {"$tasks": {"holder": "nobody", "last": 1}}, "actor": "wang"})
    )
    assert targets(planned(db, "把最后一个没人领的派给小王", [free], page)) == tasks[4:5]


def test_assigning_for_review_takes_only_tasks_waiting_for_review(db: Database) -> None:
    """The review stage is itself the condition: submitted tasks, never open ones."""
    north, _, tasks = two_projects(db)
    save(db, tasks[0], "wang")
    submit(db, tasks[0], "wang")
    review = {"$tasks": {"project": SOUTH}}
    payload = {"task_ids": review, "actor": "zhao", "stage": "review"}
    result = planned(
        db, "南区车道已经提交的任务派给小赵审核", [steps(("assign_tasks", payload))], PageContext()
    )
    assert targets(result) == tasks[0:1]
    stated = {"$tasks": {"project": SOUTH, "state": "submitted"}}
    english = planned(
        db,
        f"Send the submitted tasks of {SOUTH} to Zhao for review",
        [steps(("assign_tasks", {**payload, "task_ids": stated}))],
        PageContext(project_id=north.id),
    )
    assert targets(english) == tasks[0:1]


def _reply(db: Database, asked: IntentResult, text: str, page: PageContext) -> IntentResult:
    def complete(_request: ModelRequest) -> ModelResponse:
        message = "a picked choice is merged without the model"
        raise AssertionError(message)

    turn = PlannerTurn(text=text, actor="boss", context=page, pending=asked)
    result = plan_turn(db, turn, complete=complete, access=ModelAccess(model="m", allowed=True))
    assert result is not None
    return result


def test_a_group_that_protection_empties_is_asked_about_not_answered(db: Database) -> None:
    """All of a person's tasks hold saved work: ask to include them; picking it plans them.

    Saying all of them ("所有", "all of") already asks for them, saved work included.
    """
    _, south, tasks = two_projects(db)
    for task in tasks[0:2]:
        save(db, task, "wang")
    page = PageContext(project_id=south.id)
    revoke = steps(("revoke_assignment", {"task_id": {"$tasks": {"holder": "小王"}}}))
    asked = planned(db, "收回小王手上的任务", [revoke], page)
    assert asked.kind == "clarify", asked.text
    assert "2 条已有人工标注" in asked.text
    assert asked.clarification is not None
    assert [item.id for item in asked.clarification.candidates] == ["annotated"]
    picked = _reply(db, asked, asked.clarification.candidates[0].label, page)
    assert targets(picked) == tasks[0:2]
    english = planned(db, "Take back Wang's tasks", [revoke], page)
    assert english.kind == "clarify"
    assert "Include them too?" in english.text
    assert targets(planned(db, "收回小王手上的所有任务", [revoke], page)) == tasks[0:2]
    assert targets(planned(db, "Take back all of Wang's tasks", [revoke], page)) == tasks[0:2]


def test_a_review_of_a_task_not_waiting_for_review_says_why(db: Database) -> None:
    """Saved but not submitted: answered with the reason, alone, in a group and in English."""
    _, south, tasks = two_projects(db)
    save(db, tasks[0], "wang")
    page = PageContext(project_id=south.id, task_id=tasks[0])
    approve = steps(("review_task", {"task_id": tasks[0], "decision": "approve"}))
    result = planned(db, "这条通过", [approve], page, actor="zhao")
    assert result.kind == "answer", result.text
    assert "还没提交" in result.text
    english = planned(db, "Approve this task", [approve], page, actor="zhao")
    assert "not waiting for review" in english.text
    group = {"$tasks": {"numbers": [1, 3]}}
    both = steps(("review_task", {"task_id": group, "decision": "approve"}))
    mixed = planned(db, "第 1 条和第 3 条都通过", [both], page, actor="zhao")
    assert mixed.kind == "answer", mixed.text
    assert "其中 1 条任务没在等审核" in mixed.text


def test_a_release_tag_the_dataset_has_is_never_published_again(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same tag, in any letter case, asks: the existing one or a new tag."""
    _, south, _ = two_projects(db)
    published = ReleaseView.model_construct(id="r-1", dataset_id=south.dataset_id, tag="v1.0.0")

    def releases(_db: Database, dataset: str) -> list[ReleaseView]:
        return [published] if dataset == south.dataset_id else []

    monkeypatch.setattr("datakeel.intents.duplicates.list_releases", releases)
    release = {"dataset_id": south.dataset_id, "version_id": south.version_id}
    again = steps(("publish_release", {**release, "tag": "V1.0.0"}))
    result = planned(db, "把这个数据集发布成 V1.0.0", [again], PageContext())
    assert result.kind == "clarify", result.text
    assert "已经有一个叫「v1.0.0」的发布版本" in result.text
    assert "换个版本号" in result.text
    english = planned(db, "Publish it as release v1.0.0", [again], PageContext())
    assert "already a release" in english.text
    fresh = steps(("publish_release", {**release, "tag": "v1.1.0"}))
    page = PageContext(dataset_id=south.dataset_id)
    assert planned(db, "发布成 v1.1.0", [fresh], page).kind == "plan"


def test_a_pre_label_model_that_cannot_draw_boxes_is_said_and_box_models_offered(
    db: Database,
) -> None:
    """A polygon model: what it does, and the models that can run, alone and in a chain.

    FIX5 (11.2-5): said as "cannot" with the alternative, never rewritten as a question.
    """
    _, south, _ = two_projects(db)
    run = ServiceRunner(db)
    for model, name, kind in (("boxer", "Boxer", "box"), ("shaper", "Shaper", "polygon")):
        payload = {"id": model, "name": name, "version": "1.0", "provider": "fake"}
        run("register_model", {"model": {**payload, "capabilities": [kind]}}, "boss")
    page = PageContext(project_id=south.id)
    prelabel = ("run_prelabel", {"project_id": south.id, "model_id": "shaper"})
    result = planned(db, "用 Shaper 给这个项目跑预标注", [steps(prelabel)], page)
    assert result.kind == "answer", result.text
    assert "多边形" in result.text
    assert "做不了" in result.text
    assert "Boxer" in result.text
    assert result.clarification is None
    english = planned(db, "Pre-label this project with Shaper", [steps(prelabel)], page)
    assert "only runs box models" in english.text
    lease = ("configure_project", {"project_id": south.id, "lease_minutes": 30})
    chained = planned(
        db, "领取时限改成 30 分钟, 再用 Shaper 跑预标注", [steps(lease, prelabel)], page
    )
    assert chained.kind == "plan", chained.text
    assert chained.chain is not None
    assert [step.action for step in chained.chain.steps] == ["configure_project"]
    assert "多边形" in chained.text
    boxed = ("run_prelabel", {"project_id": south.id, "model_id": "boxer"})
    assert planned(db, "用 Boxer 跑预标注", [steps(boxed)], page).kind == "plan"


def test_role_cards_name_actions_and_permissions_in_words(db: Database) -> None:
    """A role's allowed actions and scopes read as their spoken names on the card."""
    two_projects(db)
    role = {
        "name": "验收员",
        "allowed_actions": ["accept_package"],
        "scopes": ["production:accept"],
    }
    said = "Create a role called 验收员 that can only accept packages"
    result = planned(db, said, [steps(("define_role", role))], PageContext())
    assert result.kind == "plan", result.text
    values = " ".join(shown(result).values())
    assert action_title("accept_package", "zh") in values
    assert "accept_package" not in values
    assert "production:accept" not in values
    assert NORTH not in values
    catalog = build_catalog(db, None)
    assert leaks("accept_package", "zh", allowed_words(catalog, said)) == ["accept_package"]
    assert not leaks("frame_001.png", "zh", allowed_words(catalog, "看下 frame_001.png"))


def test_a_read_about_a_numbered_task_reads_that_task(db: Database) -> None:
    """A task said as #4, 第 4 个 or a numbers group, under task_id or a made-up key."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    said = "这个项目第 4 个任务现在在谁手上"
    for params in (
        {"kind": "task", "task_id": "#4"},
        {"kind": "task", "tasks": {"$tasks": {"numbers": [4]}}},
    ):
        read = steps(("production_objects", params), kind="answer")
        result = planned(db, said, [read], page)
        assert result.kind == "answer", result.text
        assert result.answer is not None
        assert result.answer.arguments.get("task_id") == tasks[3]
        assert result.text.startswith("找到 1 个任务")
    named = {"kind": "task", "project": SOUTH, "task_id": "第 4 个"}
    english = planned(
        db,
        f"Who has task 4 of {SOUTH} now?",
        [steps(("production_objects", named), kind="answer")],
        PageContext(),
    )
    assert english.answer is not None, english.text
    assert english.answer.arguments.get("task_id") == tasks[3]
    for job in ({"task_id": {"$tasks": {"numbers": [4]}}}, {"task_id": tasks[3]}):
        # get_task reads processing jobs; a production task is read as a production object.
        read = steps(("get_task", job), kind="answer")
        result = planned(db, said, [read], page)
        assert result.answer is not None, result.text
        assert result.answer.function == "production_objects"
        assert result.answer.arguments.get("task_id") == tasks[3]
    two = {"kind": "task", "task_id": {"$tasks": {"numbers": [3, 4]}}}
    asked = planned(
        db, "第 3、4 个任务在谁手上", [steps(("production_objects", two), kind="answer")], page
    )
    assert asked.kind == "clarify"
