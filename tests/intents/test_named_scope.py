# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named objects win over the page, and every list counts in one order."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.dataset_store.dataset_service import list_files
from datakeel.dataset_store.display_order import ordered_task_rows
from datakeel.storage.intent_reads import task_snapshots
from datakeel.storage.production_objects import production_objects
from datakeel.storage.production_queries import list_packages, list_tasks
from datakeel.storage.production_rows import ProductionTaskRow
from tests.intents.planning_support import (
    SOUTH,
    descending_ids,
    planned,
    shown,
    steps,
    targets,
    two_projects,
)

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def test_a_project_named_in_the_words_wins_over_the_page(db: Database) -> None:
    """On North's page, 南区车道 in the sentence means 南区车道, in selectors and identities."""
    north, south, tasks = two_projects(db)
    page = PageContext(project_id=north.id)
    third = {"$tasks": {"project": SOUTH, "package": {"$nth": 3}}}
    result = planned(
        db,
        "把南区车道第三个包派给小王",
        [steps(("assign_tasks", {"task_ids": third, "actor": "小王"}))],
        page,
    )
    assert targets(result) == tasks[4:6]
    copied = {"$tasks": {"project_id": north.id, "package": {"$nth": 3}}}
    result = planned(
        db,
        "把南区车道第三个包派给小王",
        [steps(("assign_tasks", {"task_ids": copied, "actor": "小王"}))],
        page,
    )
    assert targets(result) == tasks[4:6]
    lease = steps(("configure_project", {"project_id": north.id, "lease_minutes": 45}))
    result = planned(db, "把南区车道的领取时限改成 45 分钟", [lease], page)
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params.get("project_id") == south.id
    unsaid = steps(("configure_project", {"lease_minutes": 45}))
    result = planned(db, "把南区车道的领取时限改成 45 分钟", [unsaid], page)
    assert result.chain is not None, result.text
    assert result.chain.steps[0].params.get("project_id") == south.id


def test_a_named_project_wins_inside_a_chain_and_in_english(db: Database) -> None:
    """Every step of a chain, in either language, uses the project the words name."""
    north, south, tasks = two_projects(db)
    page = PageContext(project_id=north.id)
    chain = steps(
        ("configure_project", {"project_id": north.id, "lease_minutes": 45}),
        ("assign_tasks", {"task_ids": {"$tasks": {"package": {"$nth": 3}}}, "actor": "wang"}),
    )
    result = planned(
        db,
        f"Set the lease of {SOUTH} to 45 minutes and give its third package to Wang",
        [chain],
        page,
    )
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params.get("project_id") == south.id
    assert "上一步完成后再规划" in result.text
    assignment = steps(
        ("assign_tasks", {"task_ids": {"$tasks": {"package": {"$nth": 3}}}, "actor": "wang"})
    )
    later = planned(db, f"Give the third package of {SOUTH} to Wang", [assignment], page)
    assert targets(later) == tasks[4:6]
    read = steps(("project_progress", {"project_id": north.id}), kind="answer")
    answer = planned(db, f"How far along is {SOUTH}?", [read], page)
    assert answer.kind == "answer", answer.text
    assert answer.answer is not None
    assert answer.answer.arguments.get("project_id") == south.id


def test_a_package_name_only_one_project_has_fixes_the_project(db: Database) -> None:
    """A package named "<project> Package 3" is found although the page is another project."""
    north, _, tasks = two_projects(db)
    named = {"$tasks": {"package": f"{SOUTH} Package 3"}}
    result = planned(
        db,
        f"把{SOUTH} Package 3 派给小王",
        [steps(("assign_tasks", {"task_ids": named, "actor": "小王"}))],
        PageContext(project_id=north.id),
    )
    assert targets(result) == tasks[4:6]


def test_lists_reads_and_the_planner_count_in_one_display_order(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identities sort backwards here; the list, reads, objects and #N still agree."""
    descending_ids(monkeypatch)
    _, south, tasks = two_projects(db)
    packages = list_packages(db, south.id)
    assert [package.name for package in packages] == ["Package 1", "Package 2", "Package 3"]
    assert [package.id for package in packages] != sorted(package.id for package in packages)
    assert tasks != sorted(tasks)
    assert [task.id for task in task_snapshots(db, south.id)] == tasks
    query = ProductionObjectQuery(kind="production_task", project_id=south.id, limit=20)
    assert [item.asset_ref.asset_id for item in production_objects(db, query)] == tasks
    query = ProductionObjectQuery(kind="task_package", project_id=south.id, limit=20)
    found = [item.asset_ref.asset_id for item in production_objects(db, query)]
    assert found == [package.id for package in packages]
    with db.session() as session:
        rows = session.query(ProductionTaskRow).filter_by(project_id=south.id).all()
        assert [row.id for row in ordered_task_rows(session, south.id, rows)] == tasks
    second = {"$tasks": {"package": {"$nth": 3}}}
    result = planned(
        db,
        "把第三个包派给小王",
        [steps(("assign_tasks", {"task_ids": second, "actor": "小王"}))],
        PageContext(project_id=south.id),
    )
    assert targets(result) == tasks[4:6]
    assert "2 个任务: #5、#6" in shown(result).values()
    english = planned(
        db,
        "Give tasks #5 and #6 to Wang",
        [steps(("assign_tasks", {"task_ids": ["#5", "#6"], "actor": "wang"}))],
        PageContext(project_id=south.id),
    )
    assert targets(english) == tasks[4:6]
    assert [task.id for task in list_tasks(db, south.id)] == tasks
    files = [item.id for item in list_files(db, south.dataset_id)]
    assert [task.sample_id for task in list_tasks(db, south.id)] == files
