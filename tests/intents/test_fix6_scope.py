# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX6: one reasonable scope answered, named settings asked by value, evidence not ready."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.storage.production_queries import list_projects
from tests.intents.fix3_support import SOUTH, planned, steps, two_projects

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_own_work_in_one_project_is_answered_for_it_and_says_so(db: Database) -> None:
    """Own work in one project is answered for it and says so."""
    two_projects(db)  # 小王 is in both projects but holds work only in 南区车道
    read = steps(("project_progress", {}), kind="answer")
    mine = planned(db, "我手上那个项目的进度怎么样?", [read], PageContext(), actor="wang")
    assert mine.kind == "answer", mine.text
    assert mine.text.startswith(f"按你所在的「{SOUTH}」项目")
    general = planned(db, "进度怎么样了", [read], PageContext(), actor="wang")
    assert general.kind == "clarify"


def asked_project(db: Database) -> str:
    """Asked project."""
    return next(project.id for project in list_projects(db) if project.name == SOUTH)


def test_a_named_setting_is_asked_for_its_value_with_the_allowed_ones(db: Database) -> None:
    """A named setting is asked for its value with the allowed ones."""
    two_projects(db)
    change = steps(("configure_project", {"project_id": SOUTH}))
    asked = planned(db, "把南区车道的派单方式改一下", [change], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.text.startswith("派单方式要改成什么")
    assert asked.clarification is not None
    assert [item.label for item in asked.clarification.candidates] == [
        "指定人",
        "按技能派",
        "自己领",
    ]
    south = PageContext(project_id=asked_project(db))
    english = planned(db, "Change the lease of this project", [change], south)
    assert english.text.startswith("What should lease (minutes) become?"), english.text


def test_a_missing_file_selection_offers_files_or_datasets(db: Database) -> None:
    """A missing file selection offers files or datasets."""
    north, south, _ = two_projects(db)
    quarantine = steps(("quarantine_files", {}))
    asked = planned(db, "把那张图隔离", [quarantine], PageContext())
    assert asked.clarification is not None
    assert {item.id for item in asked.clarification.candidates} >= {
        north.dataset_id,
        south.dataset_id,
    }
    on_page = planned(db, "把那张图隔离", [quarantine], PageContext(dataset_id=south.dataset_id))
    assert on_page.clarification is not None
    assert on_page.clarification.candidates
    assert {item.kind for item in on_page.clarification.candidates} == {"file"}


def test_near_duplicates_not_yet_computed_are_said_to_be_computing(db: Database) -> None:
    """Near duplicates not yet computed are said to be computing."""
    _, south, _ = two_projects(db)
    near = {"selection": {"$files": {"kind": "near_duplicates"}}}
    result = planned(
        db,
        "把近重复的图隔离",
        [steps(("quarantine_files", near))],
        PageContext(dataset_id=south.dataset_id),
    )
    assert "还在计算" in result.text
    assert "没有找到" not in result.text


def test_a_none_that_names_the_one_action_that_does_it_is_checked_as_it(db: Database) -> None:
    """A none that names the one action that does it is checked as it."""
    two_projects(db)
    nothing = {"kind": "none", "reason": "unsupported", "related": ["finalize_project"]}
    result = planned(db, "Finalize 南区车道", [nothing], PageContext())
    assert "平台没有" not in result.text
    assert "没通过审核" in result.text, result.text


def test_a_none_weighing_several_actions_stays_missing(db: Database) -> None:
    """The model named two close actions and why neither does it: the feature is missing."""
    two_projects(db)
    nothing = {
        "kind": "none",
        "reason": "no recurring schedule",
        "related": ["assign_tasks", "configure_project"],
    }
    result = planned(
        db, "Schedule 南区车道 to auto-assign every Monday at 9am", [nothing], PageContext()
    )
    assert result.kind == "unsupported", result.text
