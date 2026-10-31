# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3: tasks named by file, numbers in a described group, and what earlier steps change."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.storage.database import DatasetRow
from datakeel.storage.dataset_service import list_files
from datakeel.storage.production_queries import list_tasks
from tests.intents.fix3_support import planned, steps, targets, two_projects
from tests.production_helpers import production_fixture
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database


def _file_names(db: Database, project: Project, names: list[str]) -> None:
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(DatasetRow, project.dataset_id)
        assert row is not None
        row.files = [
            {**item, "filename": name} for item, name in zip(row.files, names, strict=False)
        ]
        session.commit()


def test_a_task_named_by_its_file_is_that_task(db: Database) -> None:
    """dock-04 is the task showing dock-04.png; a name two projects share is asked."""
    north, south, tasks = two_projects(db)
    _file_names(db, south, [f"dock-{index:02d}.png" for index in range(1, 7)])
    _file_names(db, north, ["dock-03.png", "north-02.png", "north-03.png", "north-04.png"])
    said = {
        "kind": "plan",
        "steps": [
            {
                "id": "s1",
                "action": "review_task",
                "params": {"decision": "approve"},
                "said": {"task_id": "dock-04"},
            }
        ],
    }
    result = planned(db, "dock-04 那张看过了, 没毛病, 过", [said], PageContext(), actor="zhao")
    assert targets(result) == tasks[3:4]
    named = steps(("review_task", {"task_id": "dock-04.png", "decision": "approve"}))
    assert targets(planned(db, "dock-04.png 过", [named], PageContext(), actor="zhao")) == [
        tasks[3]
    ]
    shared = steps(("review_task", {"task_id": "dock-03", "decision": "approve"}))
    asked = planned(db, "dock-03 那张过", [shared], PageContext(), actor="zhao")
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert len(asked.clarification.candidates) == 2


def test_numbers_that_are_not_places_narrow_the_described_group(db: Database) -> None:
    """#1 到 #5 里没人领的: only #5, not Wang's #1 #2 taken as said."""
    _, south, tasks = two_projects(db)
    group = {"$tasks": {"numbers": [1, 2, 3, 4, 5], "holder": "nobody"}}
    give = steps(("assign_tasks", {"task_ids": group, "actor": "li"}))
    result = planned(db, "#1 到 #5 里没人领的派给小李", [give], PageContext(project_id=south.id))
    assert targets(result) == tasks[4:5]


def test_a_version_that_follows_its_label_set_is_not_asked(db: Database) -> None:
    """Adding a label with no label set said asks for the label set only, with choices."""
    two_projects(db)
    edit = steps(("create_label_set", {"operation": "update", "add_labels": ["其他"]}))
    asked = planned(db, "给标签集加个「其他」标签", [edit], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert asked.clarification.fields == ["label_set_id"]
    assert asked.clarification.candidates
    assert "版本" not in asked.text


def test_an_earlier_step_changes_what_later_steps_may_do(db: Database) -> None:
    """An upgrade lets a personal project take assignments; a re-enabled account takes work."""
    _, south, tasks = two_projects(db)
    solo, _ = production_fixture(db, "personal", count=2)
    run = ServiceRunner(db)
    binding = {"operation": "bind_role", "user_id": "wang", "role_id": "annotator"}
    run("manage_users", {**binding, "project_id": solo.id}, "boss")
    work = [task.id for task in list_tasks(db, solo.id)]
    upgrade = ("upgrade_project", {"project_id": solo.id, "workflow_tier": "group"})
    give = ("assign_tasks", {"task_ids": work, "actor": "wang"})
    here = PageContext(project_id=solo.id)
    both = planned(db, "先升成小组档, 再把两条都派给小王", [steps(upgrade, give)], here)
    assert both.kind == "plan", both.text
    assert both.chain is not None
    assert [step.action for step in both.chain.steps] == ["upgrade_project", "assign_tasks"]
    assert targets(both, 1) == work
    alone = planned(db, "把两条都派给小王", [steps(give)], here)
    assert alone.kind == "answer"
    assert "个人档" in alone.text
    down = steps(("upgrade_project", {"project_id": south.id, "workflow_tier": "group"}))
    lowered = planned(db, "把南区车道降回小组档", [down], PageContext())
    assert lowered.kind == "answer"
    assert "只能往上升" in lowered.text
    run("manage_users", {"operation": "update", "user_id": "wang", "status": "disabled"}, "boss")
    enable = ("manage_users", {"operation": "update", "user_id": "wang", "status": "active"})
    hand = ("assign_tasks", {"task_ids": tasks[4:6], "actor": "小王"})
    page = PageContext(project_id=south.id)
    back = planned(db, "把小王的账号启用, 再把 5、6 派给他", [steps(enable, hand)], page)
    assert back.kind == "plan", back.text
    assert back.chain is not None
    assert len(back.chain.steps) == 2
    assert targets(back, 1) == tasks[4:6]
    disabled = planned(db, "把 5、6 派给小王", [steps(hand)], page)
    assert disabled.kind == "clarify"
    assert "已停用" in disabled.text


def test_a_quarantine_change_that_changes_nothing_is_already_so(db: Database) -> None:
    """Lifting a quarantine a file does not have is answered, not planned."""
    _, south, _ = two_projects(db)
    first = list_files(db, south.dataset_id)[0].id
    chosen = {"field": "id", "operator": "in", "value": [first]}
    selection = {"dataset_id": south.dataset_id, "filters": [chosen]}
    lift = steps(("unquarantine_files", {"selection": selection}))
    result = planned(db, "这张的隔离撤了吧", [lift], PageContext(dataset_id=south.dataset_id))
    assert result.kind == "answer", result.text
    assert "已经是这样" in result.text
