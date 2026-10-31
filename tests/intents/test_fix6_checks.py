# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX6: preconditions and current states for every state-changing action, and the exit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.intent_models import Candidate, Clarification, IntentResult, PageContext
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.preconditions import NEEDS, PRECONDITIONS, REASONS
from datakeel.intents.public_text import _FALLBACK, public, public_result
from datakeel.storage.production_queries import get_project
from tests.intents.fix3_support import SOUTH, planned, steps, two_projects

if TYPE_CHECKING:
    from datakeel.storage.database import Database

# Actions that act on a project, package or task; each declares what it needs.
WORK = frozenset({"project_id", "task_id", "task_ids", "package_id"})
PEOPLE = frozenset({"define_role", "update_role", "manage_users"})  # bindings, not work state


def test_every_registered_action_on_work_declares_its_preconditions() -> None:
    """Every registered action on work declares its preconditions."""
    acting = {
        name for name, model in PARAMETER_TYPES.items() if WORK & set(model.model_fields)
    } - PEOPLE
    assert acting <= set(NEEDS)
    assert {need for needs in NEEDS.values() for need in needs} <= set(PRECONDITIONS)
    assert all(zh and en for zh, en in REASONS.values())


def _said(db: Database, text: str, step: tuple[str, dict[str, object]], actor: str) -> str:
    """Said."""
    result = planned(db, text, [steps(step)], PageContext(), actor=actor)
    assert result.kind != "plan", result.text
    return result.text


@pytest.mark.parametrize(
    ("text", "step", "actor", "words"),
    [
        (
            "把南区车道定稿",
            ("finalize_project", {"project_id": SOUTH}),
            "boss",
            ("没通过审核", "先"),
        ),
        (
            "Accept the first package of North Crossing",
            ("accept_package", {"package_id": {"$nth": 1}}),
            "boss",
            ("only team projects",),
        ),
        (
            "南区车道第一包验收",
            ("accept_package", {"package_id": {"$nth": 1}}),
            "boss",
            ("没通过审核", "先"),
        ),
        (
            "提交南区车道第一条",
            ("submit_task", {"task_id": {"$tasks": {"project": SOUTH, "numbers": [1]}}}),
            "wang",
            ("没有可提交的标注", "先标注并保存"),
        ),
        (
            "Hand in task 5 of 南区车道",
            ("submit_task", {"task_id": {"$tasks": {"project": SOUTH, "numbers": [5]}}}),
            "li",
            ("不在你手上", "先领取"),
        ),
        (
            "把南区车道再切一次包",
            ("split_packages", {"project_id": SOUTH}),
            "boss",
            ("已经切过包",),
        ),
    ],
)
def test_an_unmet_precondition_says_what_is_missing_and_what_first(
    db: Database, text: str, step: tuple[str, dict[str, object]], actor: str, words: tuple[str, ...]
) -> None:
    """An unmet precondition says what is missing and what first."""
    two_projects(db)
    said = _said(db, text, step, actor)
    assert all(word in said for word in words), said


def test_an_earlier_step_that_meets_the_need_lets_the_plan_through(db: Database) -> None:
    """An earlier step that meets the need lets the plan through."""
    _, _, tasks = two_projects(db)
    result = planned(
        db,
        "把南区车道第五条派给小李, 然后小李提交",
        [
            steps(
                ("assign_tasks", {"task_ids": tasks[4:5], "actor": "小李"}),
                ("save_revision", {"task_id": tasks[4], "annotations": []}),
            )
        ],
        PageContext(),
        actor="li",
    )
    assert "不在你手上" not in result.text


@pytest.mark.parametrize(
    "leaky",
    [
        "after_version 的值不允许",
        "要改的是 before_version",
        "选择: {'$ref': 's1.task_ids'}",
        "形状: box",
        "没找到叫「」的项目",
        "配置团队档没有 「」 对应的设置",
    ],
)
def test_internal_names_never_leave_and_never_become_the_blank_sentence(leaky: str) -> None:
    """Internal names never leave and never become the blank sentence."""
    shown = public(leaky, "zh", EntityCatalog(), set())
    assert shown != _FALLBACK["text"][0]
    for word in ("after_version", "before_version", "$ref", "box", "「」"):
        assert word not in shown, shown


def test_a_not_found_name_among_the_choices_is_asked_as_ambiguous() -> None:
    """A not found name among the choices is asked as ambiguous."""
    asked = Clarification(
        question="没找到叫「小王」的人, 是下面哪一个?",
        candidates=[
            Candidate(id="wang", label="小王", kind="user"),
            Candidate(id="wang2", label="小王", kind="user"),
        ],
    )
    result = IntentResult(kind="clarify", text=asked.question, request="x", clarification=asked)
    shown = public_result(result, "zh", EntityCatalog())
    assert "没找到" not in shown.text
    assert "对应多个" in shown.text


def test_a_change_to_what_is_already_so_states_the_current_state(db: Database) -> None:
    """Already so is said with the state it is in, for settings, labels and open tasks."""
    _, south, tasks = two_projects(db)
    current = get_project(db, south.id).lease_minutes
    lease = ("configure_project", {"project_id": SOUTH, "lease_minutes": current})
    same = planned(db, f"南区车道领取时限设成 {current} 分钟", [steps(lease)], PageContext())
    assert same.kind == "answer", same.text
    assert "领取时限" in same.text
    assert str(current) in same.text
    reopen = ("reopen_task", {"task_id": tasks[0]})
    still = planned(db, "把南区车道第一条重新打开", [steps(reopen)], PageContext())
    assert still.kind == "answer", still.text
    assert "还没做完" in still.text
