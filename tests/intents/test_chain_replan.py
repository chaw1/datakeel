# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replan failed steps or continue state-dependent deferred steps without re-running done work."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision
from datakeel.api.app import create_app
from datakeel.cli import parser
from datakeel.cli.intents import dispatch
from datakeel.core.intent_models import ActionChain, IntentResult, PageContext
from datakeel.intents.chains import advance_chain, replan_chain
from datakeel.storage.intent_chains import get_chain
from datakeel.storage.production_queries import list_tasks
from tests.asgi_client import TestClient
from tests.intents.planning_support import planned, steps, two_projects
from tests.intents.support import run_to_end
from tests.production_helpers import production_fixture
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    import pytest

    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database


def _deferred_solo_chain(db: Database) -> tuple[Project, ActionChain, list[str]]:
    solo, _ = production_fixture(db, "personal", count=2)
    run = ServiceRunner(db)
    run("manage_users", {"operation": "create", "user_id": "boss", "display_name": "老板"})
    run("manage_users", {"operation": "create", "user_id": "wang", "display_name": "小王"}, "boss")
    run(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "wang",
            "role_id": "annotator",
            "project_id": solo.id,
        },
        "boss",
    )
    work = [task.id for task in list_tasks(db, solo.id)]
    upgrade = ("upgrade_project", {"project_id": solo.id, "workflow_tier": "group"})
    give = ("assign_tasks", {"task_ids": work, "actor": "wang"})
    deferred = planned(
        db,
        "先升成小组档, 再把两条都派给小王",
        [steps(upgrade, give)],
        PageContext(project_id=solo.id),
    )
    assert deferred.chain is not None
    return solo, deferred.chain, work


def test_http_replan_continues_deferred_steps_idempotently(db: Database) -> None:
    """Deferred state-dependent steps plan against the updated DB and replay the same next chain."""
    two_projects(db)
    solo, _ = production_fixture(db, "personal", count=2)
    run = ServiceRunner(db)
    run(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "wang",
            "role_id": "annotator",
            "project_id": solo.id,
        },
        "boss",
    )
    work = [task.id for task in list_tasks(db, solo.id)]
    upgrade = ("upgrade_project", {"project_id": solo.id, "workflow_tier": "group"})
    give = ("assign_tasks", {"task_ids": work, "actor": "wang"})
    result = planned(
        db,
        "先升成小组档, 再把两条都派给小王",
        [steps(upgrade, give)],
        PageContext(project_id=solo.id),
    )
    assert result.chain is not None
    assert [step.action for step in result.chain.deferred_steps] == ["assign_tasks"]
    first = run_to_end(db, result.chain, "boss")
    assert first.status == "succeeded"

    client = TestClient(create_app(db))
    headers = {"X-Datakeel-Actor": "boss"}
    before_runs = len(service.list_runs(db))
    first_replan = client.post(f"/api/intents/chains/{first.id}/replan", headers=headers)
    assert first_replan.status_code == 200, first_replan.text
    continuation = IntentResult.model_validate(first_replan.json())
    assert continuation.kind == "plan"
    assert continuation.chain is not None
    assert continuation.chain.status == "planned"
    assert [step.action for step in continuation.chain.steps] == ["assign_tasks"]
    assert continuation.chain.steps[0].params["task_ids"] == work
    assert len(service.list_runs(db)) == before_runs

    second_replan = client.post(f"/api/intents/chains/{first.id}/replan", headers=headers)
    assert second_replan.status_code == 200
    assert IntentResult.model_validate(second_replan.json()).chain == continuation.chain
    assert get_chain(db, first.id).next_chain_id == continuation.chain.id

    finished = ActionChain.model_validate(
        client.post(f"/api/intents/chains/{continuation.chain.id}/run", headers=headers).json()
    )
    assert finished.status == "succeeded"
    assert [task.annotator_id for task in list_tasks(db, solo.id)] == ["wang", "wang"]


def test_failed_chain_replan_reevaluates_selector_against_live_database(db: Database) -> None:
    """When a concurrent state change makes one target invalid, replan narrows from live DB."""
    _, south, tasks = two_projects(db)
    give = (
        "assign_tasks",
        {"task_ids": {"$tasks": {"holder": "nobody"}}, "actor": "li"},
    )
    result = planned(db, "把没人领的任务派给小李", [steps(give)], PageContext(project_id=south.id))
    assert result.chain is not None
    assert result.chain.steps[0].params["task_ids"] == tasks[4:6]

    run = ServiceRunner(db)
    run("assign_tasks", {"task_ids": [tasks[4]], "actor": "wang"}, "boss")
    save(db, tasks[4], "wang")
    submit(db, tasks[4], "wang")
    failed = advance_chain(db, result.chain.id, "boss")
    assert failed.status == "failed"

    replanned = replan_chain(db, failed.id, "boss")
    assert replanned.kind == "plan"
    assert replanned.chain is not None
    assert replanned.chain.status == "planned"
    assert replanned.chain.steps[0].params["task_ids"] == [tasks[5]]
    assert advance_chain(db, replanned.chain.id, "boss").status == "succeeded"


def test_failed_step_replan_substitutes_succeeded_step_outputs_and_skips_done(db: Database) -> None:
    """Replanning keeps done step receipts via $ref without re-running step 1."""
    create = (
        "create_label_set",
        {"name": "ReplanSet", "labels": [{"id": "car", "name": "汽车"}]},
    )
    publish = (
        "publish_label_set",
        {"label_set_id": {"$ref": "s1.label_set_id"}},
    )
    result = planned(db, "建一个 ReplanSet 标签集并发布", [steps(create, publish)], PageContext())
    assert result.chain is not None
    waiting = advance_chain(db, result.chain.id, "boss")
    assert waiting.status == "awaiting_approval"
    label_set_id = waiting.steps[0].outputs["label_set_id"]
    rejected_id = waiting.steps[1].plan_ids[0]
    digest = service.get_plan(db, rejected_id).plan_digest
    service.approve_plan(
        db, rejected_id, ApprovalDecision(approve=False, plan_digest=digest, actor="boss")
    )
    failed = advance_chain(db, result.chain.id, "boss")
    assert failed.status == "failed"
    before_runs = len(service.list_runs(db))

    replanned = replan_chain(db, failed.id, "boss")
    assert replanned.kind == "plan"
    assert replanned.chain is not None
    assert [step.action for step in replanned.chain.steps] == ["publish_label_set"]
    assert replanned.chain.steps[0].params["label_set_id"] == label_set_id
    assert len(service.list_runs(db)) == before_runs
    finished = run_to_end(db, replanned.chain, "boss")
    assert finished.status == "succeeded"


def test_http_replan_guards_actor_missing_and_conflict(db: Database) -> None:
    """HTTP forbids other actors (403), missing chains (404), and non-recoverable chains (409)."""
    _, chain, _ = _deferred_solo_chain(db)
    client = TestClient(create_app(db))
    boss = {"X-Datakeel-Actor": "boss"}
    assert client.post(f"/api/intents/chains/{chain.id}/replan", headers=boss).status_code == 409
    assert (
        client.post(
            f"/api/intents/chains/{chain.id}/replan", headers={"X-Datakeel-Actor": "wang"}
        ).status_code
        == 403
    )
    assert client.post("/api/intents/chains/missing-chain/replan", headers=boss).status_code == 404

    group_project, _ = production_fixture(db, "group", count=1)
    ServiceRunner(db)(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "wang",
            "role_id": "annotator",
            "project_id": group_project.id,
        },
        "boss",
    )
    simple = planned(
        db,
        "把任务派给小王",
        [
            steps(
                (
                    "assign_tasks",
                    {"task_ids": [list_tasks(db, group_project.id)[0].id], "actor": "wang"},
                )
            )
        ],
        PageContext(project_id=group_project.id),
    )
    assert simple.chain is not None
    assert run_to_end(db, simple.chain, "boss").status == "succeeded"
    assert (
        client.post(f"/api/intents/chains/{simple.chain.id}/replan", headers=boss).status_code
        == 409
    )


def test_cli_replan_prints_deferred_continuation_chain(
    db: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI intents replan plans deferred suffix steps without running them."""
    _, chain, _ = _deferred_solo_chain(db)
    assert run_to_end(db, chain, "boss").status == "succeeded"
    dispatch(db, parser().parse_args(["intents", "replan", chain.id, "--actor", "boss"]))
    cli_result = IntentResult.model_validate_json(capsys.readouterr().out)
    assert cli_result.kind == "plan"
    assert cli_result.chain is not None
    assert [step.action for step in cli_result.chain.steps] == ["assign_tasks"]
