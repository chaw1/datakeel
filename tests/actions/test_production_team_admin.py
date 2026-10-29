# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Administrative reclaim, reopen rounds, team reads, role templates and the reaper CLI."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.actions.models import ExecuteRequest
from datakeel.cli import parser
from datakeel.cli.production import dispatch
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.core.production_models import Assignment, ProductionTask
from datakeel.core.production_team_models import LeaseStatus, ProductionSkillWorkload
from datakeel.ontology.functions import invoke_function
from datakeel.storage.identity_store import role_templates
from datakeel.storage.production_queries import get_task, list_assignments, list_revisions
from tests.production_helpers import production_fixture
from tests.production_team_ops import (
    claim,
    failure,
    save,
    set_deadline,
    submit,
    team_project,
)
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def _revoke(runner: ServiceRunner, task_id: str, actor: str) -> JsonDocument:
    return runner(
        "revoke_assignment", {"task_id": task_id, "reason": "Holder is unavailable"}, actor
    )


def test_manager_reclaims_work_assigned_to_unregistered_local(db: Database) -> None:
    """Work assigned to local before anyone registered can be reclaimed with its revisions."""
    project, tasks = production_fixture(db, "group", count=2)
    runner = ServiceRunner(db)
    runner("assign_tasks", {"task_ids": [tasks[0].id], "actor": "local"})
    revision = save(db, tasks[0].id, "local")
    runner("manage_users", {"operation": "create", "user_id": "boss"})
    for actor, role in (("pm", "project_manager"), ("ann", "annotator")):
        runner("manage_users", {"operation": "create", "user_id": actor}, "boss")
        runner(
            "manage_users",
            {"operation": "bind_role", "user_id": actor, "role_id": role, "project_id": project.id},
            "boss",
        )
    denied = failure(lambda: _revoke(runner, tasks[0].id, "ann"))
    assert isinstance(denied, AuthorizationError), denied
    details = _revoke(runner, tasks[0].id, "pm")
    ended = Assignment.model_validate(details.root)
    assert (ended.actor, ended.active, ended.end_reason) == ("local", False, "revoked")
    current = get_task(db, tasks[0].id)
    assert (current.state, current.latest_revision_id, current.round) == (
        "pending",
        revision.id,
        0,
    )
    claimed = ProductionTask.model_validate(
        runner("claim_task", {"project_id": project.id}, "ann").root, extra="ignore"
    )
    assert claimed.id == tasks[0].id
    assert [item.id for item in list_revisions(db, tasks[0].id)] == [revision.id]
    missing = failure(lambda: _revoke(runner, tasks[1].id, "pm"))
    assert isinstance(missing, NotFoundError), missing


def test_submitted_work_is_reopened_not_revoked(db: Database) -> None:
    """Revoking only applies to in-flight stages; finished work goes through reopen."""
    project, _tasks = team_project(db, count=1)
    runner = ServiceRunner(db)
    task = claim(db, project.id, "annotator-a")
    save(db, task.id, "annotator-a")
    submit(db, task.id, "annotator-a")
    error = failure(lambda: _revoke(runner, task.id, "local"))
    assert isinstance(error, ConflictError), error
    assert "reopen" in str(error)


def test_reopen_counts_a_round_only_for_finished_work(db: Database) -> None:
    """Pending and in-progress tasks keep their round; submitted and approved add one each."""
    project, tasks = production_fixture(db, "group", count=1)
    runner = ServiceRunner(db)
    task_id = tasks[0].id

    def reopen() -> ProductionTask:
        details = runner("reopen_task", {"task_id": task_id, "reason": "Generated recheck"})
        return ProductionTask.model_validate(details.root, extra="ignore")

    assert (reopen().state, get_task(db, task_id).round) == ("pending", 0)
    claim(db, project.id, "annotator-a")
    assert (reopen().state, get_task(db, task_id).round) == ("in_progress", 0)
    assert any(item.active for item in list_assignments(db, task_id))
    save(db, task_id, "annotator-a")
    submit(db, task_id, "annotator-a")
    assert (reopen().state, get_task(db, task_id).round) == ("pending", 1)
    save(db, task_id, "annotator-a")
    submit(db, task_id, "annotator-a")
    current = get_task(db, task_id)
    runner(
        "review_task",
        {"task_id": task_id, "revision_id": current.latest_revision_id, "decision": "approve"},
        "reviewer-b",
    )
    assert (reopen().state, get_task(db, task_id).round) == ("pending", 2)


def test_lease_status_reports_live_expiring_overdue_and_reclaimed(db: Database) -> None:
    """The workbench and cockpit read one projection of every running lease."""
    project, _tasks = team_project(db, count=4)
    held = [claim(db, project.id, f"annotator-{index}").id for index in range(3)]
    set_deadline(db, held[1], 60)
    set_deadline(db, held[2], -5)

    def status() -> LeaseStatus:
        result = invoke_function(db, "lease_status", JsonDocument({"project_id": project.id}))
        return LeaseStatus.model_validate(result.data)

    first = status()
    assert [view.assignment.task_id for view in first.active] == [held[1], held[0]]
    assert [view.assignment.task_id for view in first.expiring] == [held[1]]
    assert [view.assignment.task_id for view in first.overdue] == [held[2]]
    runner = ServiceRunner(db)
    _revoke(runner, held[0], "local")
    dispatch(db, parser().parse_args(["production", "reap"]))
    second = status()
    assert [view.assignment.task_id for view in second.active] == [held[1]]
    assert second.overdue == ()
    assert {(item.task_id, item.reason) for item in second.reclaimed} == {
        (held[0], "revoked"),
        (held[2], "expired"),
    }


def test_reaper_cli_evaluates_an_explicit_time(
    db: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    """Operators can rerun the reaper by hand; a future time reclaims every running lease."""
    project, _tasks = team_project(db, count=2)
    claim(db, project.id, "annotator-a")
    later = (utcnow() + timedelta(minutes=11)).isoformat()
    dispatch(db, parser().parse_args(["production", "reap", "--now", later]))
    assert json.loads(capsys.readouterr().out)["released"] == 1
    dispatch(db, parser().parse_args(["production", "reap", "--now", later]))
    assert json.loads(capsys.readouterr().out)["released"] == 0


def test_skill_workload_sums_active_and_completed_work_per_skill(db: Database) -> None:
    """Managers see per-skill load from the same counters dispatch uses."""
    project, _tasks = team_project(db, count=4)
    runner = ServiceRunner(db)
    register(runner, project.id, {"ann-1": "annotator", "ann-2": "annotator"})
    grant_skills(runner, {"ann-1": 4, "ann-2": 2})
    claim(db, project.id, "ann-1")
    done = claim(db, project.id, "ann-1")
    save(db, done.id, "ann-1")
    submit(db, done.id, "ann-1")
    claim(db, project.id, "ann-2")
    result = invoke_function(db, "skill_workload", JsonDocument({"project_id": project.id}))
    workload = ProductionSkillWorkload.model_validate(result.data)
    rows = {item.skill_id: item for item in workload.skills}
    first = rows["classify-retail-ann-1"]
    assert (first.level, first.users, first.active_assignments, first.completed_tasks) == (
        4,
        ("ann-1",),
        2,
        1,
    )
    second = rows["classify-retail-ann-2"]
    assert (second.active_assignments, second.completed_tasks) == (1, 0)


def test_new_actions_sit_in_role_templates_and_models_only_prepare(db: Database) -> None:
    """Heartbeat is annotator and reviewer work; the rest is managers'; models never execute."""
    templates = {role.id: set(role.scopes) for role in role_templates()}
    assert {"production:claim"} <= templates["annotator"] & templates["reviewer"]
    assert {"production:accept", "production:assign", "production:manage"} <= templates[
        "project_manager"
    ]
    assert templates["acceptance"] == set()
    project, _tasks = team_project(db, count=1)
    task = claim(db, project.id, "annotator-a")
    runner = ServiceRunner(db)
    plan = runner.plan("heartbeat", {"task_id": task.id}, "annotator-a")
    assert not plan.requires_approval
    model = AccessContext(actor="annotator-a", entry="mcp", scope="query")
    request = ExecuteRequest(plan_digest=plan.plan_digest, actor="annotator-a")
    refused = failure(lambda: service.execute_plan(db, plan.id, request, access=model))
    assert isinstance(refused, AuthorizationError), refused
    renewed = Assignment.model_validate(
        runner("heartbeat", {"task_id": task.id}, "annotator-a").root
    )
    assert renewed.lease_expires_at > utcnow() + timedelta(minutes=9)
