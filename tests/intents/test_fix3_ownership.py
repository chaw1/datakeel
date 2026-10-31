# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3: whose task, which place, names made earlier in the plan, and edits that keep the rest."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.answers import answer_text
from datakeel.storage.dataset_service import list_files
from datakeel.storage.identity_store import get_role
from tests.intents.fix3_support import SOUTH, planned, shown, steps, targets, two_projects
from tests.production_team_ops import save
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database


def test_review_and_own_tasks_are_found_by_who_holds_or_handed_them_in(db: Database) -> None:
    """My review, the ones Li handed in, and putting mine back without a task named."""
    _, south, tasks = two_projects(db)
    # Li also works on #5, saved but not handed in: it is not waiting for review.
    ServiceRunner(db)("assign_tasks", {"task_ids": tasks[4:5], "actor": "li"}, "boss")
    save(db, tasks[4], "li")
    page = PageContext(project_id=south.id)
    mine = {"$tasks": {"holder": "me"}}
    review = steps(("review_task", {"task_id": mine, "decision": "approve"}))
    assert targets(planned(db, "我手上待审的都通过", [review], page, actor="zhao")) == tasks[2:4]
    handed = steps(
        ("review_task", {"task_id": {"$tasks": {"holder": "小李"}}, "decision": "approve"})
    )
    assert targets(planned(db, "小李交上来的都通过", [handed], page, actor="zhao")) == tasks[2:4]
    nothing = planned(db, "我手上待审的都通过", [review], page)
    assert nothing.kind == "answer", nothing.text
    assert nothing.text.startswith("你手里没有")
    english = planned(db, "Approve everything I hold for review", [review], page)
    assert english.text.startswith("You hold no matching tasks")
    back = steps(("release_task", {"stage": "review"}))
    result = planned(db, "我手上的审核先放回去", [back], PageContext(), actor="zhao")
    assert targets(result) == tasks[2:4]
    one = planned(db, "我手上那条审核先放回去", [back], PageContext(), actor="zhao")
    assert one.kind == "clarify", one.text
    assert one.clarification is not None
    assert [item.id for item in one.clarification.candidates] == tasks[2:4]
    assert [item.label for item in one.clarification.candidates] == [f"{SOUTH} #3", f"{SOUTH} #4"]
    unsaid = planned(db, "Give my tasks back", [steps(("release_task", {}))], page, actor="zhao")
    assert targets(unsaid) == tasks[2:4]
    assert unsaid.chain is not None
    assert unsaid.chain.steps[0].params.get("stage") == "review"
    own = planned(db, "我的任务先放回去", [steps(("release_task", {}))], page, actor="wang")
    assert targets(own) == tasks[0:2]


def test_places_count_inside_a_named_package_and_from_the_end(db: Database) -> None:
    """The 2nd task of package 2, package 1's last task as said, and 倒数第二 as one task."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    second = {"$tasks": {"package": {"$nth": 3}, "numbers": [2]}}
    result = planned(
        db,
        "把第 3 个包的第 2 个任务派给小王",
        [steps(("assign_tasks", {"task_ids": second, "actor": "wang"}))],
        page,
    )
    assert targets(result) == tasks[5:6]
    listed = {"$tasks": {"package": {"$nth": 3}, "numbers": ["#6"]}}
    result = planned(
        db,
        "第 3 个包里的 #6 派给小王",
        [steps(("assign_tasks", {"task_ids": listed, "actor": "wang"}))],
        page,
    )
    assert targets(result) == tasks[5:6]
    closed = {"$tasks": {"package": {"$nth": 2}, "numbers": [2]}}
    handed = planned(
        db,
        "把第 2 个包的第 2 个任务派给小王",
        [steps(("assign_tasks", {"task_ids": closed, "actor": "wang"}))],
        page,
    )
    assert handed.kind == "answer", handed.text
    assert "已经交上去或审完" in handed.text
    last = {"$tasks": {"package": {"$nth": 1}, "last": 1}}
    revoke = steps(("revoke_assignment", {"task_id": last}))
    assert (
        targets(planned(db, "Take back the last task in package 1", [revoke], page)) == tasks[1:2]
    )
    back = {"$tasks": {"last": 2}}
    give = steps(("assign_tasks", {"task_ids": back, "actor": "li"}))
    assert targets(planned(db, "列表里倒数第二条派给小李", [give], page)) == tasks[4:5]
    assert targets(planned(db, "Give the second to last task to Li", [give], page)) == tasks[4:5]
    assert targets(planned(db, "最后两条派给小李", [give], page)) == tasks[4:6]


def test_a_name_an_earlier_step_creates_is_used_not_looked_up(db: Database) -> None:
    """A new team joined and a new account bound in the same plan."""
    north, south, _ = two_projects(db)
    team = steps(
        ("manage_users", {"operation": "create_team", "name": "质检组", "leader_id": "li"}),
        ("manage_users", {"operation": "update", "user_id": "wang", "add_team_ids": ["质检组"]}),
    )
    result = planned(db, "建个质检组让小李带, 小王也拉进去", [team], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[1].params.get("team_ids") == ["质检组"]
    account = steps(
        ("manage_users", {"operation": "create", "user_id": "chenxi", "display_name": "陈曦"}),
        (
            "manage_users",
            {
                "operation": "bind_role",
                "user_id": "chenxi",
                "role_id": "annotator",
                "project_id": SOUTH,
            },
        ),
    )
    result = planned(
        db, f"开个新账号 chenxi 叫陈曦, 让她在{SOUTH}当标注员", [account], PageContext()
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[1].params.get("project_id") == south.id
    assert north.id != south.id


def test_files_named_without_extension_find_their_dataset_and_list_in_order(db: Database) -> None:
    """Stems name files, the dataset holding them is found, and the page fixes a bad identity."""
    _, south, _ = two_projects(db)
    # Only the south dataset has a 5th and a 6th file; both datasets have 0 to 3.
    files = list_files(db, south.dataset_id)[4:6]
    stems = [item.filename.rsplit(".", 1)[0] for item in files]
    named: dict[str, JsonValue] = {"kind": "named", "names": list(reversed(stems))}
    keep = {"dataset_id": south.dataset_id, "$files": named}
    version = steps(("create_version_from_selection", {"selection": keep, "name": "春季样本"}))
    result = planned(db, "只留这三个文件存成新版本", [version], PageContext())
    assert result.kind == "plan", result.text
    listed = ", ".join(item.filename for item in files)
    assert any(listed.replace(", ", "、") in value for value in shown(result).values())
    draft = ("draft_label_set", {"name": "车辆", "topic": "车辆", "sample_ids": {"$files": named}})
    result = planned(db, "拿这三张给模型看, 出一版车辆类别草稿", [steps(draft)], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    params = result.chain.steps[0].params
    assert params.get("dataset_id") == south.dataset_id
    assert sorted(params.get("sample_ids") or []) == sorted(item.id for item in files)  # type: ignore[arg-type]
    shared = {"$files": {"kind": "named", "names": ["0", "1"]}}
    both = steps(("draft_label_set", {"name": "车辆", "topic": "车辆", "sample_ids": shared}))
    assert planned(db, "拿 0 和 1 出草稿", [both], PageContext()).kind == "clarify"
    wrong = {"dataset_id": "not-a-dataset", "filters": []}
    page = PageContext(dataset_id=south.dataset_id)
    quarantine = steps(("quarantine_files", {"selection": wrong}))
    result = planned(db, "Quarantine everything in this dataset", [quarantine], page)
    assert result.chain is not None, result.text
    selection = result.chain.steps[0].params.get("selection")
    assert isinstance(selection, dict)
    assert selection.get("dataset_id") == south.dataset_id


def test_edits_keep_what_the_words_leave_unsaid(db: Database) -> None:
    """A role keeps its permissions when one is added; a model keeps its name and kind."""
    two_projects(db)
    run = ServiceRunner(db)
    payload = {"id": "boxer", "name": "Boxer", "version": "1.0", "provider": "fake"}
    run("register_model", {"model": {**payload, "capabilities": ["box"]}}, "boss")
    edit = steps(("update_model", {"model": {"id": "boxer", "version": "1.2"}}))
    result = planned(db, "Boxer 的版本号改成 1.2", [edit], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    model = result.chain.steps[0].params.get("model")
    assert isinstance(model, dict)
    assert (model.get("name"), model.get("version"), model.get("capabilities")) == (
        "Boxer",
        "1.2",
        ["box"],
    )
    assert shown(result).get("模型") == "Boxer 1.2 (框)"
    held = set(get_role(db, "reviewer").scopes)
    grant = steps(("update_role", {"role_id": "reviewer", "allowed_actions": ["export_dataset"]}))
    result = planned(db, "审核员这个角色再加上导出数据集的权限", [grant], PageContext())
    assert result.chain is not None, result.text
    scopes = result.chain.steps[0].params.get("scopes")
    assert isinstance(scopes, list)
    assert held < set(map(str, scopes))
    assert "datasets:export" in scopes
    assert "说明" not in shown(result)


def test_a_role_without_a_project_and_a_team_already_led_so(db: Database) -> None:
    """A role for someone in two projects is asked; on a page it is that project's."""
    north, south, _ = two_projects(db)
    bind = steps(
        ("manage_users", {"operation": "bind_role", "user_id": "wang", "role_id": "reviewer"})
    )
    asked = planned(db, "把小王升成审核员", [bind], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert {item.id for item in asked.clarification.candidates} == {north.id, south.id}
    paged = planned(db, "把小王升成审核员", [bind], PageContext(project_id=south.id))
    assert paged.chain is not None, paged.text
    assert paged.chain.steps[0].params.get("project_id") == south.id
    run = ServiceRunner(db)
    run(
        "manage_users",
        {"operation": "create_team", "team_id": "crew", "name": "码头组", "leader_id": "li"},
        "boss",
    )
    lead = steps(
        ("manage_users", {"operation": "update_team", "team_id": "crew", "leader_id": "li"})
    )
    same = planned(db, "Make Li the leader of 码头组", [lead], PageContext())
    assert same.kind == "answer", same.text


def test_lineage_is_read_by_name_and_said_in_words(db: Database) -> None:
    """An asset said by its name is read; the answer counts kinds and operations, no ids."""
    _, south, _ = two_projects(db)
    read = steps(("get_lineage", {"asset_id": SOUTH, "direction": "both"}), kind="answer")
    result = planned(db, f"{SOUTH}是从哪来的", [read], PageContext())
    assert result.kind == "answer", result.text
    assert result.answer is not None
    assert result.answer.arguments.get("asset_id") == south.id
    data: JsonValue = {
        "nodes": [
            {"asset_type": "dataset", "label": "码头照片", "id": "d-1"},
            {"asset_type": "action_run", "label": "create_project", "id": "r-1"},
        ],
        "truncated": False,
    }
    sentence = answer_text("get_lineage", data, "zh")
    assert sentence.startswith("上下游涉及: 数据集 1 个")
    assert "create_project" not in sentence
    assert "r-1" not in sentence
