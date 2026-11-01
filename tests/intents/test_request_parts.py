# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parts that cannot or need not be done, and values said loosely."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.answers import answer_text, run_read
from datakeel.intents.signatures import near_choice
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import DatasetRow
from datakeel.storage.dataset_service import list_files
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_queries import list_packages, list_tasks
from tests.intents.planning_support import planned, steps, two_projects
from tests.production_helpers import production_fixture
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database

PHOTOS = "南区照片"


def _renamed(db: Database, dataset_id: str, name: str) -> None:
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(DatasetRow, dataset_id)
        assert row is not None
        row.name = name
        session.commit()


def test_a_personal_project_says_it_keeps_no_assignments(db: Database) -> None:
    """Alone the part is answered with the reason; in a chain it is set aside and said."""
    _, south, _ = two_projects(db)
    personal, _ = production_fixture(db, "personal", count=2)
    mine = [task.id for task in list_tasks(db, personal.id)]
    assign = ("assign_tasks", {"task_ids": mine, "actor": "wang"})
    alone = planned(db, "把这两条派给小王", [steps(assign)], PageContext(project_id=personal.id))
    assert alone.kind == "answer", alone.text
    assert "个人档项目不派单" in alone.text
    english = planned(db, "Give both to Wang", [steps(assign)], PageContext(project_id=personal.id))
    assert english.text.startswith("A personal project has no assignments")
    lease = ("configure_project", {"project_id": south.id, "lease_minutes": 45})
    both = planned(
        db, "南区领取时限改成 45 分钟, 再把那两条派给小王", [steps(lease, assign)], PageContext()
    )
    assert both.kind == "plan", both.text
    assert both.chain is not None
    assert [step.action for step in both.chain.steps] == ["configure_project"]
    assert "个人档项目不派单" in both.text
    assert any("个人档项目不派单" in note for note in both.chain.notes)


def test_a_part_that_changes_nothing_or_matches_nothing_is_set_aside(db: Database) -> None:
    """Taking back a task nobody holds, or a group that is empty, never reaches the card."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    revoke = ("revoke_assignment", {"task_id": tasks[4], "reason": "重新派"})
    assign = ("assign_tasks", {"task_ids": [tasks[4]], "actor": "wang"})
    result = planned(db, "把第 5 条收回来再派给小王", [steps(revoke, assign)], page)
    assert result.kind == "answer", result.text
    assert result.chain is None
    assert "没有人领着" in result.text
    assert "上一步完成后再规划" in result.text
    alone = planned(db, "把第 5 条收回来", [steps(revoke)], page)
    assert alone.kind == "answer", alone.text
    lease = ("configure_project", {"project_id": south.id, "lease_minutes": 45})
    empty = {"$tasks": {"package": {"$nth": 2}, "unassigned": True}}
    chain = steps(lease, ("assign_tasks", {"task_ids": empty, "actor": "wang"}))
    result = planned(db, "领取时限改成 45 分钟, 再把第二个包没人领的派给小王", [chain], page)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert [step.action for step in result.chain.steps] == ["configure_project"]
    assert "没有符合条件的任务" in result.text


def test_one_value_said_where_a_list_is_taken_becomes_a_list(db: Database) -> None:
    """A single issue sentence is one issue, not a type error to ask about."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id, task_id=tasks[2])
    rework = ("review_task", {"task_id": tasks[2], "decision": "rework", "issues": "框画歪了"})
    result = planned(db, "这条退回, 框画歪了", [steps(rework)], page, actor="zhao")
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params.get("issues") == ["框画歪了"]


def test_a_numbered_package_without_a_project_offers_each_project_s_package(db: Database) -> None:
    """Package 2 exists in both projects: asked with both; package 3 only in one: taken."""
    north, south, _ = two_projects(db)
    second = {"package_id": {"$nth": 2}, "project_id": None}
    asked = planned(db, "领一个 Package 2 的任务", [steps(("claim_task", second))], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    wanted = {list_packages(db, project.id)[1].id for project in (north, south)}
    assert {item.id for item in asked.clarification.candidates} == wanted
    third = {"package_id": {"$nth": 3}}
    taken = planned(db, "领一个 Package 3 的任务", [steps(("claim_task", third))], PageContext())
    assert taken.kind == "plan", taken.text
    assert taken.chain is not None
    assert taken.chain.steps[0].params.get("package_id") == list_packages(db, south.id)[2].id


def test_an_edit_without_a_change_asks_what_to_change(db: Database) -> None:
    """A person, a skill or a project to edit with nothing new is a question, never a card."""
    _, south, _ = two_projects(db)
    person = steps(("manage_users", {"operation": "update", "user_id": "wang"}))
    asked = planned(db, "把小王的技能改一下", [person], PageContext())
    assert asked.kind == "clarify", asked.text
    assert "可以改" in asked.text
    assert "技能" in asked.text
    english = planned(db, "Change Wang's settings", [person], PageContext())
    assert "You can change" in english.text
    project = steps(("configure_project", {"project_id": south.id}))
    assert planned(db, "改一下南区车道的设置", [project], PageContext()).kind == "clarify"


def test_files_are_found_in_the_dataset_the_words_or_selection_name(db: Database) -> None:
    """No page: the selection's dataset, or the one the sentence names, holds the files."""
    _, south, _ = two_projects(db)
    _renamed(db, south.dataset_id, PHOTOS)
    named = {"$files": {"kind": "named", "names": ["1.png"]}}
    for selection, said in (
        ({**named, "dataset_id": south.dataset_id}, "Quarantine 1.png"),
        ({**named, "dataset_id": PHOTOS}, "Quarantine 1.png"),
        (named, f"把{PHOTOS}里的 1.png 隔离"),
    ):
        step = steps(("quarantine_files", {"selection": selection}))
        result = planned(db, said, [step], PageContext())
        assert result.kind == "plan", (said, result.text)
        assert result.chain is not None
        chosen = result.chain.steps[0].params.get("selection")
        assert isinstance(chosen, dict)
        assert chosen.get("dataset_id") == south.dataset_id
        assert chosen.get("limit") == 1


def test_a_draft_version_can_be_compared_and_unanswerable_asks_are_plain(db: Database) -> None:
    """Comparing with a draft is a read; an unanswerable question is said in words."""
    _, south, _ = two_projects(db)
    with db.session() as session:
        db.lock_writes(session)
        first = session.get(ProductionLabelSetRow, f"{south.label_set_id}:1")
        assert first is not None
        payload = {**first.payload, "version": 2, "published": False}
        row = ProductionLabelSetRow(
            id=f"{south.label_set_id}:2",
            label_set_id=south.label_set_id,
            version=2,
            published=False,
            payload=payload,
        )
        session.add(row)
        session.commit()
    arguments = {"label_set_id": south.label_set_id, "before_version": 1, "after_version": 2}
    context = ToolCallContext(actor="boss")
    answer, _ = run_read(db, "label_set_diff", dict(arguments), context, "zh")
    assert answer is not None
    data = {"status": "unanswerable", "message": "无法用已登记指标回答。", "assertions": []}
    assert "已登记的指标回答不了" in answer_text("ask_data", data, "zh")
    assert "assertions" not in answer_text("ask_data", data, "en")


def test_review_tasks_and_remaining_files_are_the_ones_meant(db: Database) -> None:
    """His review tasks are held for review; the rest are the files not selected."""
    _, south, tasks = two_projects(db)
    stop = ("manage_users", {"operation": "update", "user_id": "zhao", "status": "disabled"})
    revoke = (
        "revoke_assignment",
        {"task_id": {"$tasks": {"holder": "zhao"}}, "stage": "review", "reason": "停用"},
    )
    result = planned(db, "停用小赵, 再把他手上的审核任务收回", [steps(stop, revoke)], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert [step.action for step in result.chain.steps] == ["manage_users", "revoke_assignment"]
    assert [item.get("task_id") for item in result.chain.steps[1].items] == tasks[2:4]
    files = [item.id for item in list_files(db, south.dataset_id)]
    page = PageContext(
        dataset_id=south.dataset_id, selected_ids=tuple(files[:2]), selected_kind="file"
    )
    rest = steps(("quarantine_files", {"selection": {"$files": {"kind": "remaining"}}}))
    result = planned(db, "把没选中的其余文件隔离", [rest], page)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    chosen = result.chain.steps[0].params.get("selection")
    assert isinstance(chosen, dict)
    assert chosen.get("limit") == len(files) - 2
    assert near_choice("production_objects", "kind", "tasks") == "production_task"
    assert near_choice("production_objects", "kind", "packages") == "task_package"


def test_a_publish_nobody_asked_for_is_never_added(db: Database) -> None:
    """A project on a label set uses its newest published version; no publish is slipped in."""
    _, south, _ = two_projects(db)
    _renamed(db, south.dataset_id, PHOTOS)
    page = PageContext(label_set_id=south.label_set_id)
    project = {"name": "新车道", "dataset_id": south.dataset_id, "label_set_id": south.label_set_id}
    slipped = steps(
        ("publish_label_set", {"label_set_id": south.label_set_id}),
        ("create_project", {**project, "label_set_version": {"$ref": "s1.label_set_version"}}),
    )
    plain = steps(("create_project", project))
    said = f"用{PHOTOS}和这个标签集新建一个项目叫新车道"
    result = planned(db, said, [slipped, plain], page)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert [step.action for step in result.chain.steps] == ["create_project"]
    assert result.chain.steps[0].params.get("label_set_version") == 1
    stubborn = planned(db, said, [slipped], page)
    assert stubborn.kind == "clarify"
    assert "没说要发布" in stubborn.text


def test_places_names_and_choices_said_in_words_are_understood(db: Database) -> None:
    """「第 3 个包」, a dataset by name, 「分类标注」 and a label's letter case all resolve."""
    _, south, tasks = two_projects(db)
    third = {"$tasks": {"project": "南区车道", "package": "第 3 个包", "holder": "nobody"}}
    assign = steps(("assign_tasks", {"task_ids": third, "actor": "wang"}))
    result = planned(db, "把南区车道第 3 个包里没人领的派给小王", [assign], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params.get("task_ids") == tasks[4:6]
    _renamed(db, south.dataset_id, PHOTOS)
    wipe = steps(("delete_files", {"selection": {"dataset_id": PHOTOS}}))
    result = planned(db, f"Delete every image in {PHOTOS}", [wipe], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    chosen = result.chain.steps[0].params.get("selection")
    assert isinstance(chosen, dict)
    assert chosen.get("dataset_id") == south.dataset_id
    unknown = steps(("delete_files", {"selection": {"dataset_id": "不存在的照片"}}))
    asked = planned(db, "Delete every image in 不存在的照片", [unknown], PageContext())
    assert asked.kind == "clarify", asked.text
    assert near_choice("manage_skills", "annotation_type", "分类标注") == "classification"
    assert near_choice("manage_skills", "annotation_type", "框选") == "box"
    assert near_choice("review_task", "decision", "不通过") == "不通过"
    label = {"id": "rust", "name": "锈病", "name_en": "Rust"}
    receipt = ServiceRunner(db)("create_label_set", {"name": "叶子", "labels": [label]}, "boss")
    made = str(receipt.root.get("label_set_id") or receipt.root.get("id"))
    same = {"label_set_id": made, "labels": [{**label, "name_en": "rust", "name_zh": "锈病"}]}
    edit = steps(("create_label_set", same))
    again = planned(db, "把叶子的标签改成锈病", [edit], PageContext(label_set_id=made))
    assert again.kind == "answer", again.text
