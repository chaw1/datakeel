# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team dispatch: three strategies, skill levels, least load, determinism and load limits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.production_models import Assignment, ProductionTask
from datakeel.storage.production_queries import get_project, list_assignments, list_tasks
from datakeel.storage.production_rows import ProductionAssignmentRow
from tests.production_helpers import production_fixture
from tests.production_team_ops import failure
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datakeel.core.models import JsonDocument
    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database

REQUIREMENT = {"annotation_type": "classification", "domain": "retail", "min_level": 3}
LEVELS = {"ann-1": 3, "ann-2": 2, "ann-3": 5, "ann-4": 3}


def _team(
    db: Database, count: int, levels: Mapping[str, int] = LEVELS, **settings: object
) -> tuple[ServiceRunner, Project, tuple[ProductionTask, ...]]:
    project, tasks = production_fixture(db, "team", count=count)
    runner = ServiceRunner(db)
    register(runner, project.id, dict.fromkeys(levels, "annotator") | {"pm": "project_manager"})
    grant_skills(runner, levels)
    runner(
        "configure_project",
        {"project_id": project.id, "skill_requirement": REQUIREMENT, **settings},
        "pm",
    )
    return runner, get_project(db, project.id), tasks


def _assignments(details: JsonDocument) -> list[Assignment]:
    values = details.root["assignments"]
    assert isinstance(values, list)
    return [Assignment.model_validate(item) for item in values]


def _reference(
    task_ids: list[str], levels: Mapping[str, int], loads: dict[str, int], limit: int | None
) -> dict[str, str]:
    """Independent restatement: qualify by level, then least load, then smallest identity."""
    pool = sorted(actor for actor, level in levels.items() if level >= REQUIREMENT["min_level"])
    current = {actor: loads.get(actor, 0) for actor in pool}
    expected: dict[str, str] = {}
    for task_id in sorted(task_ids):
        open_people = [actor for actor in pool if limit is None or current[actor] < limit]
        if not open_people:
            continue
        chosen = min(open_people, key=lambda actor: (current[actor], actor))
        expected[task_id] = chosen
        current[chosen] += 1
    return expected


def test_skill_dispatch_matches_the_documented_rule_and_skips_low_levels(db: Database) -> None:
    """Level 2 never receives level-3 work; equal people balance by load, then by identity."""
    runner, project, tasks = _team(db, 9, dispatch_strategy="skill")
    preclaimed = ProductionTask.model_validate(
        runner("claim_task", {"project_id": project.id}, "ann-3").root, extra="ignore"
    )
    details = runner(
        "assign_tasks",
        {"task_ids": [task.id for task in tasks], "strategy": "skill"},
        "pm",
    )
    assigned = _assignments(details)
    remaining = [task.id for task in tasks if task.id != preclaimed.id]
    expected = _reference(remaining, LEVELS, {"ann-3": 1}, None)
    assert {item.task_id: item.actor for item in assigned} == expected
    assert {item.dispatch for item in assigned} == {"skill"}
    assert "ann-2" not in {item.actor for item in assigned}
    assert details.root["unassigned"] == [
        {"task_id": preclaimed.id, "reason": "task_state_not_dispatchable"}
    ]
    counts = {actor: list(expected.values()).count(actor) for actor in ("ann-1", "ann-3", "ann-4")}
    assert counts == {"ann-1": 3, "ann-3": 2, "ann-4": 3}


def test_skill_level_filter_admits_the_exact_minimum_and_rejects_below(db: Database) -> None:
    """A level-3 person may claim level-3 work; a level-2 person is refused explicitly."""
    runner, project, _tasks = _team(db, 3, dispatch_strategy="skill")
    error = failure(lambda: runner("claim_task", {"project_id": project.id}, "ann-2"))
    assert isinstance(error, AuthorizationError), error
    assert "level 3" in str(error)
    claimed = ProductionTask.model_validate(
        runner("claim_task", {"project_id": project.id}, "ann-1").root, extra="ignore"
    )
    assert claimed.project_id == project.id
    lowered = {**REQUIREMENT, "min_level": 2}
    details = runner(
        "assign_tasks",
        {
            "task_ids": [task.id for task in list_tasks(db, project.id) if task.id != claimed.id],
            "strategy": "skill",
            "skill_requirement": lowered,
            "candidates": ["ann-2"],
        },
        "pm",
    )
    assert {item.actor for item in _assignments(details)} == {"ann-2"}


def test_batch_dispatch_never_exceeds_the_per_person_limit(db: Database) -> None:
    """Ten tasks and three qualified people at limit two give six assignments and four skips."""
    runner, _project, tasks = _team(db, 10, dispatch_strategy="skill", max_active_tasks=2)
    details = runner(
        "assign_tasks", {"task_ids": [task.id for task in tasks], "strategy": "skill"}, "pm"
    )
    assigned = _assignments(details)
    counts = {actor: [item.actor for item in assigned].count(actor) for actor in LEVELS}
    assert counts == {"ann-1": 2, "ann-2": 0, "ann-3": 2, "ann-4": 2}
    assert {item.task_id: item.actor for item in assigned} == _reference(
        [task.id for task in tasks], LEVELS, {}, 2
    )
    skipped = details.root["unassigned"]
    assert isinstance(skipped, list)
    assert len(skipped) == 4
    assert all(
        isinstance(item, dict) and item["reason"] == "load_limit_reached" for item in skipped
    )
    again = failure(
        lambda: runner(
            "assign_tasks", {"task_ids": [task.id for task in tasks], "strategy": "skill"}, "pm"
        )
    )
    assert isinstance(again, ConflictError), again


def test_named_batches_and_claims_respect_the_same_limit(db: Database) -> None:
    """A named batch above the limit is rejected whole; a claim at the limit is refused."""
    runner, project, tasks = _team(db, 4, dispatch_strategy="claim", max_active_tasks=2)
    over = failure(
        lambda: runner(
            "assign_tasks", {"task_ids": [task.id for task in tasks[:3]], "actor": "ann-1"}, "pm"
        )
    )
    assert isinstance(over, ConflictError), over
    assert str(over) == (
        "ann-1 holds 0 active annotation tasks; adding 3 would exceed the limit of 2"
    )
    assert all(not list_assignments(db, task.id) for task in tasks)
    runner("assign_tasks", {"task_ids": [tasks[0].id], "actor": "ann-1"}, "pm")
    runner("claim_task", {"project_id": project.id}, "ann-1")
    refused = failure(lambda: runner("claim_task", {"project_id": project.id}, "ann-1"))
    assert isinstance(refused, ConflictError), refused
    assert str(refused) == (
        "ann-1 holds 2 active annotation tasks; adding 1 would exceed the limit of 2"
    )
    runner("claim_task", {"project_id": project.id}, "ann-2")


def test_three_strategies_write_one_assignment_table_with_their_source(db: Database) -> None:
    """Manager assignment, skill dispatch and self-claim are rows of the same table."""
    runner, project, tasks = _team(db, 3, dispatch_strategy="assign")
    blocked = failure(lambda: runner("claim_task", {"project_id": project.id}, "ann-1"))
    assert isinstance(blocked, ValidationError), blocked
    runner("assign_tasks", {"task_ids": [tasks[0].id], "actor": "ann-2"}, "pm")
    runner("configure_project", {"project_id": project.id, "dispatch_strategy": "skill"}, "pm")
    runner("assign_tasks", {"task_ids": [tasks[1].id], "strategy": "skill"}, "pm")
    runner("configure_project", {"project_id": project.id, "dispatch_strategy": "claim"}, "pm")
    runner("claim_task", {"project_id": project.id}, "ann-2")
    with db.session() as session:
        rows = session.scalars(select(ProductionAssignmentRow)).all()
        sources = {
            row.task_id: (row.actor, Assignment.model_validate(row.payload).dispatch)
            for row in rows
        }
    assert sources == {
        tasks[0].id: ("ann-2", "assign"),
        tasks[1].id: ("ann-1", "skill"),
        tasks[2].id: ("ann-2", "claim"),
    }
    duplicate = failure(
        lambda: runner("assign_tasks", {"task_ids": [tasks[2].id], "strategy": "skill"}, "pm")
    )
    assert isinstance(duplicate, ConflictError), duplicate


def test_skill_strategy_needs_a_requirement_and_team_tier(db: Database) -> None:
    """Skill matching is a team rule; group projects and missing requirements are rejected."""
    project, tasks = production_fixture(db, "group", count=2)
    runner = ServiceRunner(db)
    error = failure(
        lambda: runner(
            "assign_tasks",
            {"task_ids": [tasks[0].id], "strategy": "skill", "skill_requirement": REQUIREMENT},
        )
    )
    assert isinstance(error, ValidationError), error
    team, _team_tasks = production_fixture(db, "team", count=1)
    missing = failure(
        lambda: runner("configure_project", {"project_id": team.id, "dispatch_strategy": "skill"})
    )
    assert isinstance(missing, ValidationError), missing
    assert get_project(db, project.id).dispatch_strategy == "claim"
