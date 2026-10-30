# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A person's load is only open annotation work, and one dispatch may only lower the limit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.production_team_models import ProductionSkillWorkload
from datakeel.core.workbench_models import SkillDispatchPreviewRequest
from datakeel.ontology.functions import invoke_function
from datakeel.storage.production_dispatch_rules import active_loads
from datakeel.storage.production_queries import get_project, list_assignments
from datakeel.storage.workbench_assignees import assignees
from datakeel.storage.workbench_samples import dispatch_preview
from tests.asgi_client import TestClient
from tests.production_flow_support import action_payload
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, failure, review, save, submit, team_project
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    from datakeel.core.production_models import ProductionTask, Project
    from datakeel.storage.database import Database

LIMIT = 2
REQUIREMENT = {"annotation_type": "classification", "domain": "retail", "min_level": 1}
TOO_HIGH = (
    "max_active_tasks 50 for this dispatch is above the project setting of 2; "
    "a dispatch may use 2 or a lower limit"
)


def _caller(actor: str) -> AccessContext:
    return AccessContext(actor=actor, entry="ask", scope="query")


def _loads(db: Database, project_id: str) -> dict[str, int]:
    with db.session() as session:
        return active_loads(session, project_id, "annotation")


def _skill_team(
    db: Database, count: int
) -> tuple[ServiceRunner, Project, tuple[ProductionTask, ...]]:
    project, tasks = production_fixture(db, "team", count=count)
    runner = ServiceRunner(db)
    register(runner, project.id, {"ann": "annotator", "rev": "reviewer", "pm": "project_manager"})
    grant_skills(runner, {"ann": 1})
    runner(
        "configure_project",
        {"project_id": project.id, "skill_requirement": REQUIREMENT, "max_active_tasks": LIMIT},
        "pm",
    )
    return runner, get_project(db, project.id), tasks


def test_submitted_work_frees_the_limit_and_returned_rework_counts_again(db: Database) -> None:
    """At limit two, two submissions let the person claim two more; rework is open again."""
    project, _tasks = team_project(db, count=8, max_active_tasks=LIMIT)
    first = [claim(db, project.id, "ann") for _ in range(LIMIT)]
    refused = failure(lambda: claim(db, project.id, "ann"))
    assert isinstance(refused, ConflictError), refused
    assert (
        str(refused) == "ann holds 2 active annotation tasks; adding 1 would exceed the limit of 2"
    )
    for task in first:
        save(db, task.id, "ann")
        submit(db, task.id, "ann")
    assert _loads(db, project.id) == {}
    second = [claim(db, project.id, "ann") for _ in range(LIMIT)]
    assert {task.id for task in second}.isdisjoint({task.id for task in first})
    assert _loads(db, project.id) == {"ann": LIMIT}
    assert isinstance(failure(lambda: claim(db, project.id, "ann")), ConflictError)
    returned = claim(db, project.id, "rev", "review")
    review(db, returned.id, "rev", approve=False)
    assert [item.actor for item in list_assignments(db, returned.id) if item.active] == ["ann"]
    assert _loads(db, project.id) == {"ann": LIMIT + 1}


def test_a_dispatch_limit_above_the_project_setting_is_refused_before_signing(
    db: Database,
) -> None:
    """Named and skill dispatch with 50 over a project limit of 2 fail at preparation."""
    runner, project, tasks = _skill_team(db, 4)
    task_ids = [task.id for task in tasks]
    for target in ({"actor": "ann"}, {"strategy": "skill"}):
        error = failure(
            lambda target=target: runner.plan(
                "assign_tasks", {"task_ids": task_ids, "max_active_tasks": 50, **target}, "pm"
            )
        )
        assert isinstance(error, ValidationError), error
        assert str(error) == TOO_HIGH
    preview = failure(
        lambda: dispatch_preview(
            db,
            project.id,
            _caller("pm"),
            SkillDispatchPreviewRequest(task_ids=tuple(task_ids), max_active_tasks=50),
        )
    )
    assert isinstance(preview, ValidationError), preview
    assert str(preview) == TOO_HIGH
    response = TestClient(create_app(db)).post(
        "/api/actions/assign_tasks/prepare",
        json=action_payload(
            "assign_tasks", {"task_ids": task_ids, "actor": "ann", "max_active_tasks": 50}
        ).root,
        headers={"X-Datakeel-Actor": "pm"},
    )
    assert response.status_code == 422, response.text
    assert "project setting of 2" in response.text
    assert all(not list_assignments(db, task_id) for task_id in task_ids)


def test_a_lower_dispatch_limit_binds_named_and_skill_dispatch(db: Database) -> None:
    """A request may use the project limit or a lower one; the lower one is what is enforced."""
    runner, _project, tasks = _skill_team(db, 4)
    over = failure(
        lambda: runner(
            "assign_tasks",
            {"task_ids": [tasks[0].id, tasks[1].id], "actor": "ann", "max_active_tasks": 1},
            "pm",
        )
    )
    assert isinstance(over, ConflictError), over
    assert str(over) == "ann holds 0 active annotation tasks; adding 2 would exceed the limit of 1"
    runner(
        "assign_tasks", {"task_ids": [tasks[0].id], "actor": "ann", "max_active_tasks": LIMIT}, "pm"
    )
    skill = failure(
        lambda: runner(
            "assign_tasks",
            {"task_ids": [tasks[1].id, tasks[2].id], "strategy": "skill", "max_active_tasks": 1},
            "pm",
        )
    )
    assert isinstance(skill, ConflictError), skill
    assert str(skill) == "No task could be dispatched: load_limit_reached"
    runner(
        "assign_tasks",
        {"task_ids": [tasks[1].id], "strategy": "skill", "max_active_tasks": LIMIT},
        "pm",
    )
    assert _loads(db, tasks[0].project_id) == {"ann": LIMIT}


def test_picker_preview_and_skill_workload_count_the_same_open_work(db: Database) -> None:
    """After one of two claims is submitted, every read reports one open task for the person."""
    _runner, project, tasks = _skill_team(db, 4)
    held = [claim(db, project.id, "ann") for _ in range(LIMIT)]
    save(db, held[0].id, "ann")
    submit(db, held[0].id, "ann")
    picker = assignees(db, project.id, _caller("pm"), "annotation")
    assert {person.actor: person.current for person in picker.people}["ann"] == 1
    workload = ProductionSkillWorkload.model_validate(
        invoke_function(
            db, "skill_workload", JsonDocument.model_validate({"project_id": project.id})
        ).data
    )
    assert [(skill.users, skill.active_assignments) for skill in workload.skills] == [(("ann",), 1)]
    preview = dispatch_preview(
        db,
        project.id,
        _caller("pm"),
        SkillDispatchPreviewRequest(
            task_ids=tuple(task.id for task in tasks if task.id not in {item.id for item in held})
        ),
    )
    assert [(item.actor, item.current) for item in preview.people] == [("ann", 1)]
