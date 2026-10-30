# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named assignment in the cockpit: work held by unregistered `local` goes to a listed person."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.workbench_models import WorkbenchAssignees
from datakeel.storage.production_queries import list_assignments, list_tasks
from datakeel.storage.workbench_assignees import assignees
from tests.asgi_client import TestClient
from tests.production_helpers import production_fixture
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _caller(actor: str) -> AccessContext:
    return AccessContext(actor=actor, entry="ask", scope="query")


def _free_task(db: Database, project_id: str) -> str:
    return next(task.id for task in list_tasks(db, project_id) if not _active(db, task.id))


def _active(db: Database, task_id: str) -> list[str]:
    return [item.actor for item in list_assignments(db, task_id) if item.active]


def _local_work_then_team(db: Database) -> tuple[str, tuple[str, ...], ServiceRunner]:
    """Zero-user work held by `local`; people register afterwards and the project goes team."""
    project, tasks = production_fixture(db, "group", count=4)
    runner = ServiceRunner(db)
    held = tuple(task.id for task in tasks[:3])
    runner("assign_tasks", {"task_ids": list(held), "actor": "local"})
    save(db, held[0], "local")
    runner("manage_users", {"operation": "create", "user_id": "boss"})
    for actor, role in (("pm", "project_manager"), ("ann", "annotator"), ("rev", "reviewer")):
        runner("manage_users", {"operation": "create", "user_id": actor}, "boss")
        runner(
            "manage_users",
            {"operation": "bind_role", "user_id": actor, "role_id": role, "project_id": project.id},
            "boss",
        )
    runner("upgrade_project", {"project_id": project.id, "workflow_tier": "team"}, "boss")
    return project.id, held, runner


def test_assignees_list_registered_stage_people_with_load_not_local(db: Database) -> None:
    """Annotation lists people with annotate authority and their load; review lists reviewers."""
    project_id, _, boss = _local_work_then_team(db)
    free = _free_task(db, project_id)
    boss("assign_tasks", {"task_ids": [free], "actor": "ann"}, "boss")
    listed = assignees(db, project_id, _caller("boss"), "annotation")
    people = {person.actor: person.current for person in listed.people}
    assert "local" not in people
    assert "rev" not in people
    assert people["ann"] == 1
    assert "boss" in people
    review = assignees(db, project_id, _caller("boss"), "review")
    assert "rev" in {person.actor for person in review.people}
    assert "ann" not in {person.actor for person in review.people}


def test_local_work_is_revoked_and_assigned_by_name_then_finished(db: Database) -> None:
    """Every task `local` holds can be taken back and handed to a listed annotator who submits."""
    project_id, held, boss = _local_work_then_team(db)
    for task_id in held:
        boss("revoke_assignment", {"task_id": task_id, "reason": "local left"}, "boss")
    listed = assignees(db, project_id, _caller("boss"), "annotation")
    assert listed.people[0].current == 0
    boss("assign_tasks", {"task_ids": list(held), "actor": "ann"}, "boss")
    for task_id in held:
        assert _active(db, task_id) == ["ann"]
    save(db, held[0], "ann")
    assert submit(db, held[0], "ann").annotator_id == "ann"
    listed = assignees(db, project_id, _caller("boss"), "annotation")
    # The load matches what dispatch limits count: the stage assignment stays until review.
    assert {person.actor: person.current for person in listed.people}["ann"] == len(held)


def test_assignees_route_reads_actor_header_and_rejects_outsiders(db: Database) -> None:
    """The cockpit reads the list over HTTP; someone who cannot assign is refused."""
    project_id, _, _ = _local_work_then_team(db)
    client = TestClient(create_app(db))
    response = client.get(
        f"/api/production/projects/{project_id}/assignees",
        params={"stage": "annotation"},
        headers={"X-Datakeel-Actor": "pm"},
    )
    assert response.status_code == 200
    value = WorkbenchAssignees.model_validate(response.json())
    assert "ann" in {person.actor for person in value.people}
    refused = client.get(
        f"/api/production/projects/{project_id}/assignees",
        headers={"X-Datakeel-Actor": "ann"},
    )
    assert refused.status_code == 403
    with pytest.raises(AuthorizationError):
        assignees(db, project_id, _caller("rev"), "annotation")


def test_assignees_mutation_guard(db: Database) -> None:
    """One measured anchor: only assigners see the list, and only stage-scoped people are on it."""
    project_id, _, _ = _local_work_then_team(db)
    actors = [
        person.actor for person in assignees(db, project_id, _caller("boss"), "annotation").people
    ]
    assert "rev" not in actors
    assert "ann" in actors
    with pytest.raises(AuthorizationError):
        assignees(db, project_id, _caller("ann"), "annotation")
