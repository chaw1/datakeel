# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workbench file names, filename search, team review queue, task status and dispatch preview."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.actions.production_parameters import UpgradeProjectParams
from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_models import Assignment
from datakeel.core.workbench_models import (
    SkillDispatchPreview,
    SkillDispatchPreviewRequest,
    WorkbenchProjectQuery,
    WorkbenchTaskSamples,
    WorkbenchTaskStatus,
)
from datakeel.storage.database import VersionRow
from datakeel.storage.production_projects import upgrade_project
from datakeel.storage.production_queries import get_project, list_assignments
from datakeel.storage.production_rows import ProductionAssignmentRow
from datakeel.storage.workbench_reads import workbench_project
from datakeel.storage.workbench_samples import dispatch_preview, task_status
from tests.asgi_client import TestClient
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, heartbeat, revoke, save, submit, team_project
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    from datakeel.core.production_models import ProductionTask, Project
    from datakeel.storage.database import Database


def _caller(actor: str = "local") -> AccessContext:
    return AccessContext(actor=actor, entry="ask", scope="query")


def _filenames(db: Database, project: Project) -> dict[str, str]:
    with db.session() as session:
        version = session.get(VersionRow, project.version_id)
        assert version is not None
        return {item["id"]: item["filename"] for item in version.manifest}


def test_workbench_search_filters_file_names_before_paging(db: Database) -> None:
    """A case-insensitive name search narrows the whole project before the page is cut."""
    project, tasks = production_fixture(db, "group", count=12)
    names = _filenames(db, project)
    matching = [task.id for task in tasks if "1" in names[task.sample_id]]
    first = workbench_project(db, project.id, _caller(), WorkbenchProjectQuery(search="1", limit=2))
    assert [task.id for task in first.tasks] == matching[:2]
    assert first.next_cursor == matching[1]
    rest = workbench_project(
        db,
        project.id,
        _caller(),
        WorkbenchProjectQuery(search="1", limit=2, cursor=first.next_cursor),
    )
    assert [task.id for task in rest.tasks] == matching[2:]
    assert len(matching) == 3
    upper = workbench_project(db, project.id, _caller(), WorkbenchProjectQuery(search="PNG"))
    assert len(upper.tasks) == len(tasks)
    none = workbench_project(db, project.id, _caller(), WorkbenchProjectQuery(search="zzz"))
    assert none.tasks == ()


def test_workbench_names_each_page_task_by_file_name_not_server_path(db: Database) -> None:
    """Every listed task carries its manifest file name; the private materialized path is absent."""
    project, tasks = production_fixture(db, "group", count=3)
    names = _filenames(db, project)
    value = workbench_project(db, project.id, _caller())
    assert {item.task_id: item.name for item in value.task_samples} == {
        task.id: names[task.sample_id] for task in tasks
    }
    assert all(item.path == item.name for item in value.task_samples)
    assert "generated/" not in value.model_dump_json()


def test_team_review_queue_omits_tasks_the_reviewer_annotated(db: Database) -> None:
    """Team separation hides own work from the queue; the group tier keeps self-review."""
    project, _tasks = team_project(db, count=2)
    own = claim(db, project.id, "annotator-a")
    save(db, own.id, "annotator-a")
    submit(db, own.id, "annotator-a")
    other = claim(db, project.id, "annotator-c")
    save(db, other.id, "annotator-c")
    submit(db, other.id, "annotator-c")
    query = WorkbenchProjectQuery(view="review")
    mine = workbench_project(db, project.id, _caller("annotator-a"), query)
    assert [task.id for task in mine.tasks] == [other.id]
    reviewer = workbench_project(db, project.id, _caller("reviewer-b"), query)
    assert {task.id for task in reviewer.tasks} == {own.id, other.id}
    group, _ = production_fixture(db, "group", count=1)
    task = claim(db, group.id, "annotator-a")
    save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    assert [
        item.id for item in workbench_project(db, group.id, _caller("annotator-a"), query).tasks
    ] == [task.id]


def _column(db: Database, assignment_id: str) -> float | None:
    with db.session() as session:
        row = session.get(ProductionAssignmentRow, assignment_id)
        assert row is not None
        return row.lease_expires_at


def test_task_status_reports_enforced_lease_and_revocation(db: Database) -> None:
    """Polling sees the running lease, its renewal and then the revoke release with its reason."""
    project, _tasks = team_project(db, count=1)
    task = claim(db, project.id, "annotator-a")
    status = task_status(db, task.id, _caller())
    assert len(status.leases) == 1
    lease = status.leases[0]
    assert (lease.actor, lease.stage, lease.enforced) == ("annotator-a", "annotation", True)
    column = _column(db, lease.assignment_id)
    assert column is not None
    assert abs(lease.expires_at.timestamp() - column) < 1e-3
    expected = (lease.expires_at - status.observed_at).total_seconds()
    assert abs(lease.seconds_remaining - expected) < 1e-3
    assert 0 < lease.seconds_remaining <= project.lease_minutes * 60
    renewed = heartbeat(db, task.id, "annotator-a")
    assert task_status(db, task.id, _caller()).leases[0].expires_at == renewed.lease_expires_at
    revoke(db, task.id)
    after = task_status(db, task.id, _caller())
    assert after.leases == ()
    assert after.task.state == "pending"
    assert after.assignments == list_assignments(db, task.id)
    assert [item.end_reason for item in after.assignments] == ["revoked"]
    assert [(item.reason, item.actor) for item in after.releases] == [("revoked", "annotator-a")]


def test_task_status_reports_the_deadline_a_team_upgrade_restarted(db: Database) -> None:
    """After an upgrade the status shows the enforced deadline, not the stale recorded one."""
    project, _tasks = production_fixture(db, "group", count=1)
    task = claim(db, project.id, "annotator-a")
    group = task_status(db, task.id, _caller()).leases[0]
    assert not group.enforced
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalars(select(ProductionAssignmentRow)).one()
        stale = Assignment.model_validate(row.payload).model_copy(
            update={"lease_expires_at": utcnow() - timedelta(minutes=30)}
        )
        row.payload = stale.model_dump(mode="json")
        session.commit()
    with db.session() as session:
        db.lock_writes(session)
        upgrade_project(
            session,
            UpgradeProjectParams(request_id=new_id(), project_id=project.id, workflow_tier="team"),
        )
        session.commit()
    lease = task_status(db, task.id, _caller()).leases[0]
    assert lease.enforced
    assert lease.expires_at > utcnow() + timedelta(minutes=project.lease_minutes - 1)
    assert lease.seconds_remaining > 0


def test_task_status_lists_no_lease_once_the_stage_waits_for_review(db: Database) -> None:
    """A retained annotation assignment of a submitted task is not a running lease."""
    project, _tasks = team_project(db, count=1)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    submitted = submit(db, task.id, "annotator-a")
    status = task_status(db, task.id, _caller())
    assert status.task == submitted
    assert status.leases == ()
    assert [item.active for item in status.assignments] == [True]


REQUIREMENT = {"annotation_type": "classification", "domain": "retail", "min_level": 3}


def _skill_team(
    db: Database, count: int
) -> tuple[ServiceRunner, Project, tuple[ProductionTask, ...]]:
    project, tasks = production_fixture(db, "team", count=count)
    runner = ServiceRunner(db)
    levels = {"ann-1": 3, "ann-2": 2, "ann-3": 5}
    register(runner, project.id, dict.fromkeys(levels, "annotator") | {"pm": "project_manager"})
    grant_skills(runner, levels)
    runner(
        "configure_project",
        {"project_id": project.id, "skill_requirement": REQUIREMENT, "max_active_tasks": 2},
        "pm",
    )
    return runner, get_project(db, project.id), tasks


def test_dispatch_preview_matches_the_executed_skill_dispatch(db: Database) -> None:
    """The preview names the same people, loads and skips that assign_tasks then records."""
    runner, project, tasks = _skill_team(db, 6)
    runner("claim_task", {"project_id": project.id}, "ann-3")
    requested = tuple(task.id for task in tasks)
    preview = dispatch_preview(
        db, project.id, _caller("pm"), SkillDispatchPreviewRequest(task_ids=requested)
    )
    assert preview.qualified == ("ann-1", "ann-3")
    assert preview.max_active_tasks == 2
    assert {(item.actor, item.current, item.added) for item in preview.people} == {
        ("ann-1", 0, 2),
        ("ann-3", 1, 1),
    }
    details = runner("assign_tasks", {"task_ids": list(requested), "strategy": "skill"}, "pm")
    assignments = details.root["assignments"]
    assert isinstance(assignments, list)
    executed = {
        Assignment.model_validate(item).task_id: Assignment.model_validate(item).actor
        for item in assignments
    }
    assert {item.task_id: item.actor for item in preview.picks} == executed
    skipped = details.root["unassigned"]
    assert isinstance(skipped, list)
    assert [item.model_dump(mode="json") for item in preview.unassigned] == skipped
    assert len(preview.unassigned) == 3
    assert "load_limit_reached" in {item.reason for item in preview.unassigned}
    after = dispatch_preview(
        db, project.id, _caller("pm"), SkillDispatchPreviewRequest(task_ids=requested)
    )
    assert after.picks == ()


def test_workbench_http_status_names_and_preview_endpoints(db: Database) -> None:
    """The three reads are served over HTTP with bounded inputs and project-scoped names."""
    _runner, project, tasks = _skill_team(db, 2)
    other, other_tasks = production_fixture(db, "group", count=1)
    names = _filenames(db, project)
    with TestClient(create_app(db)) as client:
        response = client.get(
            f"/api/production/projects/{project.id}/task-samples",
            params={"task_id": [tasks[0].id, other_tasks[0].id]},
        )
        assert response.status_code == 200, response.text
        samples = WorkbenchTaskSamples.model_validate(response.json())
        assert [(item.task_id, item.name) for item in samples.items] == [
            (tasks[0].id, names[tasks[0].sample_id])
        ]
        too_many = client.get(
            f"/api/production/projects/{project.id}/task-samples",
            params={"task_id": [str(index) for index in range(501)]},
        )
        assert too_many.status_code == 422
        status = client.get(f"/api/production/tasks/{tasks[0].id}/status")
        assert status.status_code == 200, status.text
        assert WorkbenchTaskStatus.model_validate(status.json()).task.id == tasks[0].id
        preview = client.post(
            f"/api/production/projects/{project.id}/dispatch-preview",
            json={"task_ids": [task.id for task in tasks]},
        )
        assert preview.status_code == 200, preview.text
        assert len(SkillDispatchPreview.model_validate(preview.json()).picks) == 2
        mismatch = client.post(
            f"/api/production/projects/{other.id}/dispatch-preview",
            json={"task_ids": [tasks[0].id]},
        )
        assert mismatch.status_code == 422
        search = client.get(
            f"/api/production/projects/{project.id}/workbench", params={"search": ""}
        )
        assert search.status_code == 422
