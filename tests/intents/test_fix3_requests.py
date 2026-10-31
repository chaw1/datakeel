# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3: one task meant, places in a group, teams as holders, states said first, take-backs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from tests.intents.fix3_support import SOUTH, planned, steps, targets, two_projects
from tests.production_team_ops import save
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_one_task_meant_is_asked_and_only_saved_work_is_handed_in(db: Database) -> None:
    """One task meant but two match: ask; hand in only saved open work; reads find mine."""
    _, south, tasks = two_projects(db)
    save(db, tasks[0], "wang")
    mine = {"$tasks": {"holder": "me", "project": SOUTH}}
    submit = steps(("submit_task", {"task_id": mine}))
    result = planned(db, "我标好的那条帮我交上去", [submit], PageContext(), actor="wang")
    assert targets(result) == tasks[0:1]
    save(db, tasks[1], "wang")
    asked = planned(db, "我标好的那条帮我交上去", [submit], PageContext(), actor="wang")
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert [item.id for item in asked.clarification.candidates] == tasks[0:2]
    read = steps(("get_task", {"task_id": {"$tasks": {"holder": "小李", "project": SOUTH}}}))
    handed = planned(db, "小李交上去的那些审到哪了", [{**read, "kind": "answer"}], PageContext())
    # Both of Li's handed-in tasks are found; a one-task read then asks which.
    assert handed.kind == "clarify", handed.text
    assert "要看哪一个" in handed.text
    nobody = steps(("get_task", {"task_id": {"$tasks": {"holder": "小赵", "untouched": True}}}))
    empty = planned(
        db, "小赵没动过的任务", [{**nobody, "kind": "answer"}], PageContext(project_id=south.id)
    )
    assert empty.kind == "answer", empty.text
    assert "没有" in empty.text


def test_numbers_in_a_described_group_and_this_package_from_the_page(db: Database) -> None:
    """Numbers outside the free tasks count among them; the same package is the page's."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    free = {"$tasks": {"holder": "nobody", "numbers": [2]}}
    give = steps(("assign_tasks", {"task_ids": free, "actor": "li"}))
    assert targets(planned(db, "没人领的任务里第 2 条给小李", [give], page)) == tasks[5:6]
    listed = {"$tasks": {"holder": "nobody", "numbers": [5]}}
    named = steps(("assign_tasks", {"task_ids": listed, "actor": "li"}))
    assert targets(planned(db, "没人领的 #5 给小李", [named], page)) == tasks[4:5]
    same = {"$tasks": {"holder": "nobody", "package": "this"}}
    paged = PageContext(project_id=south.id, task_id=tasks[4])
    together = steps(("assign_tasks", {"task_ids": same, "actor": "li"}))
    assert targets(planned(db, "跟这条同一个包里没人领的都给小李", [together], paged)) == tasks[4:6]


def test_a_team_named_as_holder_means_its_members(db: Database) -> None:
    """The tasks of a team's people (码头组的人) are the ones its members hold."""
    _, south, tasks = two_projects(db)
    run = ServiceRunner(db)
    team = {"operation": "create_team", "team_id": "crew", "name": "码头组", "leader_id": "wang"}
    run("manage_users", team, "boss")
    run("manage_users", {"operation": "update", "user_id": "wang", "team_ids": ["crew"]}, "boss")
    revoke = steps(("revoke_assignment", {"task_id": {"$tasks": {"holder": "码头组"}}}))
    result = planned(db, "码头组的人手上的任务都收回", [revoke], PageContext(project_id=south.id))
    assert targets(result) == tasks[0:2]


def test_states_the_request_cannot_change_are_said_before_planning(db: Database) -> None:
    """Reopening open work, a made-up scope, and a project on an unpublished version."""
    _, south, tasks = two_projects(db)
    reopen = steps(("reopen_task", {"task_id": tasks[4], "reason": "标错了"}))
    still = planned(db, "Reopen task 5", [reopen], PageContext(project_id=south.id))
    assert still.kind == "answer", still.text
    role = {
        "role_id": "checker",
        "name": "复核员",
        "scopes": ["review"],
        "allowed_actions": ["review_task"],
    }
    made = planned(
        db, "新建角色复核员, 只能审核任务", [steps(("define_role", role))], PageContext()
    )
    assert made.chain is not None, made.text
    assert made.chain.steps[0].params.get("scopes") == ["production:review"]
    with db.session() as session:
        db.lock_writes(session)
        first = session.get(ProductionLabelSetRow, f"{south.label_set_id}:1")
        assert first is not None
        draft = {**first.payload, "version": 2, "published": False}
        row = ProductionLabelSetRow(
            id=f"{south.label_set_id}:2",
            label_set_id=south.label_set_id,
            version=2,
            published=False,
            payload=draft,
        )
        session.add(row)
        session.commit()
    page = PageContext(dataset_id=south.dataset_id, label_set_id=south.label_set_id)
    project = {
        "name": "新项目",
        "dataset_id": south.dataset_id,
        "version_id": south.version_id,
        "label_set_id": south.label_set_id,
        "label_set_version": 2,
    }
    asked = planned(db, "用第 2 版建个项目叫新项目", [steps(("create_project", project))], page)
    assert asked.kind == "clarify", asked.text
    assert "还没有发布" in asked.text
    publish = ("publish_label_set", {"label_set_id": south.label_set_id, "version": 2})
    both = planned(db, "先发布第 2 版再建项目", [steps(publish, ("create_project", project))], page)
    assert both.kind == "plan", both.text


def test_a_task_taken_back_earlier_in_the_plan_is_free_for_the_next_step(db: Database) -> None:
    """先收回小王的, 再把没动过的都给小李: the taken-back tasks are given too, not left out."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    untouched = {"$tasks": {"untouched": True}}
    chain = steps(
        ("revoke_assignment", {"task_id": {"$tasks": {"holder": "小王"}}, "reason": "换人"}),
        ("assign_tasks", {"task_ids": untouched, "actor": "li"}),
    )
    result = planned(db, "先把小王手上的收回, 再把没动过的任务都派给小李", [chain], page)
    assert targets(result) == tasks[0:2]
    assert targets(result, 1) == [*tasks[0:2], *tasks[4:6]]
    give = steps(("assign_tasks", {"task_ids": untouched, "actor": "li"}))
    alone = planned(db, "把没动过的任务都派给小李", [give], page)
    # Without the take-back, Wang's tasks stay his.
    assert targets(alone) == tasks[4:6]
