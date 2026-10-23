# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Guard durable completion and terminal state against disconnect and startup races."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, list_runs
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.runtime import workflow_service
from datakeel.runtime.workflow_service import recover_runs, resume_workflow, start_workflow
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run, set_status
from tests.workflows.test_authorization import pause_cleanup

if TYPE_CHECKING:
    from datakeel.core.workflow_models import WorkflowCreation, WorkflowRun
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def test_closing_after_done_preserves_completed_resume_key(
    db: Database, dataset: DatasetView
) -> None:
    """A received terminal event promises durable replay even if the socket then closes."""
    run, plan = pause_cleanup(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ResumeInput(plan_id=plan.id, idempotency_key="close-after-done")
    stream = resume_workflow(db, run.id, request)
    terminal = next(event for event in stream if event.event == "done")
    stream.close()
    assert terminal.run.status == "SUCCEEDED"
    actions = list_runs(db)
    assert list(resume_workflow(db, run.id, request))[-1].run == terminal.run
    assert list_runs(db) == actions


def test_failed_run_cannot_restore_stale_approval_checkpoint(
    db: Database, dataset: DatasetView
) -> None:
    """A persisted failure must remain terminal even when an older approval checkpoint survives."""
    run, plan = pause_cleanup(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    set_status(db, run.id, "FAILED", error="Failure persisted before checkpoint update")
    before = get_run(db, run.id)
    actions = list_runs(db)
    with pytest.raises(AuthorizationError):
        list(
            resume_workflow(
                db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="failed-terminal")
            )
        )
    assert get_run(db, run.id) == before
    assert list_runs(db) == actions
    assert list_audit(db, run.id)[-1].kind == "RESUME_DENIED"


def test_start_does_not_revive_run_interrupted_before_writer_claim(
    db: Database, dataset: DatasetView, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A startup sweep between start persistence and writer claim cannot be undone by activation."""
    original = workflow_service.create_run

    def create_then_restart(
        database: Database, creation: WorkflowCreation
    ) -> tuple[WorkflowRun, bool]:
        result = original(database, creation)
        recover_runs(database)
        return result

    monkeypatch.setattr(workflow_service, "create_run", create_then_restart)
    run = list(
        start_workflow(
            db,
            "low-quality-cleanup",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id, "quality_max": 0}),
                idempotency_key="start-restart-race",
            ),
        )
    )[-1].run
    assert run.status == "INTERRUPTED"
    assert list_invocations(db, run.id) == []
    assert list_runs(db) == []


def test_replaying_start_while_original_writer_is_active_returns_same_run(
    db: Database, dataset: DatasetView
) -> None:
    """A repeated start key can inspect its active run without acquiring another execution lease."""
    request = WorkflowStart(
        inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="active-replay"
    )
    stream = start_workflow(db, "dataset-health", request)
    original = next(stream)
    replay = list(start_workflow(db, "dataset-health", request))[-1].run
    assert replay.id == original.run.id
    assert replay.status == "RUNNING"
    assert list_invocations(db, replay.id) == []
    stream.close()


def test_interrupted_nonapproval_run_cannot_resume_and_keeps_denial_audit(
    db: Database, dataset: DatasetView
) -> None:
    """Arbitrary plan payloads cannot turn interrupted ordinary execution into a recovery point."""
    stream = start_workflow(
        db,
        "dataset-health",
        WorkflowStart(
            inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="interrupted-resume"
        ),
    )
    run = next(stream).run
    stream.close()
    before = get_run(db, run.id)
    with pytest.raises(AuthorizationError):
        list(
            resume_workflow(
                db, run.id, ResumeInput(plan_id="invented-plan", idempotency_key="must-deny")
            )
        )
    assert get_run(db, run.id) == before
    assert list_invocations(db, run.id) == []
    assert list_audit(db, run.id)[-1].kind == "RESUME_DENIED"
