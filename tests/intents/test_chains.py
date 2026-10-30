# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A planned chain changes nothing until a person confirms, then runs like manual actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision
from datakeel.core.intent_models import PageContext
from datakeel.intents.chains import advance_chain
from datakeel.storage.production_queries import list_packages, list_projects
from tests.intents.support import SETUP, approve_waiting, images, plan, run_to_end

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_project_sentence_plans_four_ordered_steps_without_changing_anything(
    db: Database, tmp_path: Path
) -> None:
    """Label set, publication, project and packages are planned; nothing is prepared yet."""
    dataset = images(db, tmp_path / "images")
    result = plan(db, SETUP, PageContext(dataset_id=dataset.id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    steps = result.chain.steps
    assert [step.action for step in steps] == [
        "create_label_set",
        "publish_label_set",
        "create_project",
        "split_packages",
    ]
    assert steps[0].params["labels"] == [{"id": "label_1", "name": "红绿灯"}]
    assert steps[2].params["workflow_tier"] == "team"
    assert steps[2].params["dataset_id"] == dataset.id
    assert steps[2].params["label_set_id"] == {"$ref": "s1.label_set_id"}
    assert "10%" in str(steps[2].params["guidelines"])
    assert [step.estimate.requires_approval for step in steps] == [False, True, True, False]
    assert steps[2].estimate.object_count == 4
    assert service.list_runs(db) == []
    assert service.list_approvals(db) == []
    assert not list_projects(db)


def test_confirmed_chain_stops_for_each_signature_and_matches_manual_receipts(
    db: Database, tmp_path: Path
) -> None:
    """Irreversible steps wait in the approval queue; receipts name the person, not an agent."""
    dataset = images(db, tmp_path / "images")
    chain = plan(db, SETUP, PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    first = advance_chain(db, chain.id, "local")
    assert first.status == "awaiting_approval"
    assert [step.status for step in first.steps][:2] == ["succeeded", "awaiting_approval"]
    waiting = service.list_approvals(db)
    assert [item.action_type for item in waiting] == ["publish_label_set"]
    approve_waiting(db, first)
    finished = run_to_end(db, first)
    assert finished.status == "succeeded"
    project = list_projects(db)[0]
    assert project.workflow_tier == "team"
    assert list_packages(db, project.id)
    runs = service.list_runs(db)
    assert sorted(run.action_type for run in runs) == sorted(
        ["create_label_set", "publish_label_set", "create_project", "split_packages"]
    )
    for run in runs:
        assert run.receipt is not None
        assert run.receipt.on_behalf_of == "local"
        assert service.get_plan(db, run.plan_id).agent_id is None


def test_rejected_step_fails_and_resume_asks_for_a_new_signature(
    db: Database, tmp_path: Path
) -> None:
    """A rejection stops the chain with its reason; resuming submits a fresh plan to sign."""
    dataset = images(db, tmp_path / "images")
    chain = plan(db, SETUP, PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    waiting = advance_chain(db, chain.id, "local")
    rejected_id = waiting.steps[1].plan_ids[0]
    digest = service.get_plan(db, rejected_id).plan_digest
    service.approve_plan(
        db, rejected_id, ApprovalDecision(approve=False, plan_digest=digest, actor="local")
    )
    failed = advance_chain(db, chain.id, "local")
    assert failed.status == "failed"
    assert failed.steps[1].error == "The approver rejected this step"
    resumed = advance_chain(db, chain.id, "local")
    assert resumed.status == "awaiting_approval"
    fresh = resumed.steps[1].plan_ids[0]
    assert fresh != rejected_id
    assert service.get_plan(db, fresh).status == "PREPARED"
    assert [run.action_type for run in service.list_runs(db)] == ["create_label_set"]
