# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow recovery trusts signed durable records and preserves exactly-once effects."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, get_plan, list_runs
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import AuthorizationError, ConflictError, DatakeelError
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.workflow_models import WorkflowStart
from datakeel.runtime.workflow_service import resume_workflow, start_workflow
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run
from tests.agent.test_resume import forge_approval

if TYPE_CHECKING:
    from datakeel.actions.models import ActionPlan
    from datakeel.core.workflow_models import WorkflowRun
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView
    from tests.agent.test_resume import ForgedCase


def pause_cleanup(db: Database, dataset_id: str) -> tuple[WorkflowRun, ActionPlan]:
    """Enter a real persisted approval gate after quarantining generated low-quality files."""
    run = list(
        start_workflow(
            db,
            "low-quality-cleanup",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset_id, "quality_max": 0}),
                idempotency_key=new_id(),
            ),
        )
    )[-1].run
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    return run, get_plan(db, run.pending_plan_id)


def test_forged_workflow_resumes_are_denied_and_audited(db: Database, dataset: DatasetView) -> None:
    """Reject all five forgery classes at the recovery gate, verified by independent audit."""
    cases: tuple[ForgedCase, ...] = (
        "no_approval",
        "digest_mismatch",
        "expired",
        "actor_mismatch",
        "foreign_plan",
    )
    for case in cases:
        run, plan = pause_cleanup(db, dataset.id)
        requested = plan
        if case == "foreign_plan":
            _, requested = pause_cleanup(db, dataset.id)
            approve_plan(
                db, requested.id, ApprovalDecision(approve=True, plan_digest=requested.plan_digest)
            )
        elif case != "no_approval":
            forge_approval(db, plan, case)
        before = get_run(db, run.id)
        invocations = list_invocations(db, run.id)
        executed = list_runs(db)
        rejected: DatakeelError | None = None
        try:
            list(
                resume_workflow(db, run.id, ResumeInput(plan_id=requested.id, idempotency_key=case))
            )
        except DatakeelError as error:
            rejected = error
        audit = list_audit(db, run.id)
        denied = [entry for entry in audit if entry.kind == "RESUME_DENIED"]
        assert len(denied) == 1, (case, audit)
        assert denied[0].run_id == run.id
        assert denied[0].plan_id == requested.id
        assert denied[0].reason
        assert denied[0].id
        assert denied[0].created_at
        assert not any(entry.kind == "RESUME_AUTHORIZED" for entry in audit)
        assert isinstance(rejected, AuthorizationError), (case, rejected)
        assert get_run(db, run.id) == before
        assert list_invocations(db, run.id) == invocations
        assert list_runs(db) == executed


def test_approved_workflow_resume_replays_key_and_one_execution(
    db: Database, dataset: DatasetView
) -> None:
    """A separate resume key replays completion without another delete or tool invocation."""
    run, plan = pause_cleanup(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ResumeInput(plan_id=plan.id, idempotency_key="resume-approved")
    first = list(resume_workflow(db, run.id, request))[-1].run
    spans = list_invocations(db, run.id)
    actions = list_runs(db)
    assert first.status == "SUCCEEDED"
    assert list(resume_workflow(db, run.id, request))[-1].run == first
    assert list_invocations(db, run.id) == spans
    assert list_runs(db) == actions
    assert len([action for action in actions if action.plan_id == plan.id]) == 1
    assert Counter(item.name for item in spans)["delete_files"] == 1
    assert len([item for item in list_audit(db, run.id) if item.kind == "RESUME_AUTHORIZED"]) == 1
    with pytest.raises(ConflictError):
        list(resume_workflow(db, run.id, request.model_copy(update={"plan_id": "different-plan"})))


def test_workflow_resume_reuses_receipt_already_executed_in_approval_page(
    db: Database, dataset: DatasetView
) -> None:
    """Approval UI execution is authoritative even when it used a different operation key."""
    run, plan = pause_cleanup(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    existing = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    finished = list(
        resume_workflow(db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="ui-executed"))
    )[-1].run
    assert finished.status == "SUCCEEDED"
    deletion = next(step for step in finished.steps if step.id == "delete")
    assert deletion.output == existing.model_dump(mode="json")
    assert [action for action in list_runs(db) if action.plan_id == plan.id] == [existing]
    assert Counter(item.name for item in list_invocations(db, run.id))["delete_files"] == 1


def test_concurrent_workflow_resumes_execute_at_most_once(
    db: Database, dataset: DatasetView
) -> None:
    """Concurrent callers cannot dispatch the same pending action twice."""
    run, plan = pause_cleanup(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))

    def resume(index: int) -> str:
        try:
            return list(
                resume_workflow(
                    db, run.id, ResumeInput(plan_id=plan.id, idempotency_key=f"parallel-{index}")
                )
            )[-1].run.status
        except (AuthorizationError, ConflictError):
            return "REFUSED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(resume, range(2)))
    assert "SUCCEEDED" in outcomes
    assert set(outcomes) <= {"SUCCEEDED", "REFUSED"}
    assert len([action for action in list_runs(db) if action.plan_id == plan.id]) == 1
    assert Counter(item.name for item in list_invocations(db, run.id))["delete_files"] == 1
