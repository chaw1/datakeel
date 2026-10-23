# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable interruption recovery trusts approval rows and preserves transcript identity."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Literal

import pytest
from sqlalchemy import select

from datakeel.actions.models import ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.policy import plan_digest
from datakeel.actions.service import approve_plan, execute_plan, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import (
    create_conversation,
    get_conversation,
    resume_conversation,
    send_message,
)
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ResumeInput
from datakeel.core.errors import AuthorizationError, ConflictError, DatakeelError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.action_rows import ActionPlanRow, ApprovalRow
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.dataset_service import list_files
from datakeel.storage.tool_invocations import list_invocations
from tests.agent.test_service import action_script

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

ForgedCase = Literal["no_approval", "digest_mismatch", "expired", "actor_mismatch", "foreign_plan"]


def pause_deletion(db: Database, dataset_id: str) -> tuple[str, ActionPlan]:
    """Create an actual checkpointed approval gate using generated local source assets."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset_id))
    streamed = list(
        send_message(
            db,
            conversation.id,
            MessageInput(
                content="Delete low quality files", idempotency_key="separate-response-key"
            ),
            provider=FakeProvider(action_script(dataset_id, "delete_files")),
        )
    )
    plan = next(event.outcome.plan for event in streamed if event.event == "plan" and event.outcome)
    assert plan is not None
    assert streamed[-2].stop_reason == "approval_required"
    return conversation.id, plan


def forge_approval(db: Database, plan: ActionPlan, case: ForgedCase) -> None:
    """Use persisted fixture rows to isolate digest, expiry, and actor authorization failures."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        if case == "expired":
            expired = plan.model_copy(update={"expires_at": utcnow() - timedelta(seconds=1)})
            plan = expired.model_copy(update={"plan_digest": plan_digest(expired)})
            row.payload = plan.model_dump(mode="json")
        row.status = "APPROVED"
        session.add(
            ApprovalRow(
                plan_id=plan.id,
                plan_digest="different-digest" if case == "digest_mismatch" else plan.plan_digest,
                actor="other-actor" if case == "actor_mismatch" else plan.actor,
                status="APPROVED",
            )
        )
        session.commit()


def test_forged_resume_cases_are_denied_and_audited(db: Database, dataset: DatasetView) -> None:
    """Reject all five forgeries at recovery itself, before the executor's separate defenses."""
    cases: tuple[ForgedCase, ...] = (
        "no_approval",
        "digest_mismatch",
        "expired",
        "actor_mismatch",
        "foreign_plan",
    )
    for case in cases:
        conversation_id, plan = pause_deletion(db, dataset.id)
        requested = plan
        if case == "foreign_plan":
            _, requested = pause_deletion(db, dataset.id)
            approve_plan(
                db, requested.id, ApprovalDecision(approve=True, plan_digest=requested.plan_digest)
            )
        elif case != "no_approval":
            forge_approval(db, plan, case)
        before = get_conversation(db, conversation_id)
        invocations = list_invocations(db, conversation_id)
        provider = FakeProvider([])
        rejected: DatakeelError | None = None
        try:
            list(
                resume_conversation(
                    db,
                    conversation_id,
                    ResumeInput(plan_id=requested.id, idempotency_key=case),
                    provider=provider,
                )
            )
        except DatakeelError as error:
            rejected = error
        audit = list_audit(db, conversation_id)
        denied = [entry for entry in audit if entry.kind == "RESUME_DENIED"]
        assert len(denied) == 1, (case, audit)
        assert denied[0].conversation_id == conversation_id
        assert denied[0].plan_id == requested.id
        assert denied[0].reason
        assert denied[0].id
        assert denied[0].created_at
        assert not any(entry.kind == "RESUME_AUTHORIZED" for entry in audit)
        assert isinstance(rejected, AuthorizationError), (case, rejected)
        assert provider.requests == []
        assert get_conversation(db, conversation_id).messages == before.messages
        assert list_invocations(db, conversation_id) == invocations
        assert list_runs(db) == []


def test_resume_when_approved_executes_once_and_reports_receipt_through_workspace(
    db: Database,
    dataset: DatasetView,
) -> None:
    """A fresh graph resumes without inventing another user message or correlated tool result."""
    conversation_id, plan = pause_deletion(db, dataset.id)
    before = get_conversation(db, conversation_id)
    invocations = list_invocations(db, conversation_id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    db.engine.dispose()
    provider = FakeProvider([ModelResponse(content="Recovered receipt confirmed.")])
    request = ResumeInput(plan_id=plan.id, idempotency_key="separate-response-key")
    first = list(resume_conversation(db, conversation_id, request, provider=provider))
    after = get_conversation(db, conversation_id)
    assert [event.event for event in first] == ["receipt", "text", "done"]
    assert after.messages[:-1] == before.messages
    assert after.messages[-1].content == "Recovered receipt confirmed."
    assert after.messages[-1].role == "assistant"
    assert list_invocations(db, conversation_id) == invocations
    runs = list_runs(db)
    assert len(runs) == 1
    assert runs[0].status == "SUCCEEDED"
    assert len(list_files(db, dataset.id)) == 1
    assert (
        execute_plan(
            db,
            plan.id,
            ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id),
        )
        == runs[0]
    )
    facts = JsonDocument.model_validate_json(provider.requests[0].messages[-1].content)
    assert runs[0].id in str(facts.root["plans"])
    assert list(resume_conversation(db, conversation_id, request, provider=provider)) == first
    assert len(provider.requests) == 1
    assert get_conversation(db, conversation_id).messages == after.messages
    assert list_runs(db) == runs
    assert (
        len(
            [
                entry
                for entry in list_audit(db, conversation_id)
                if entry.kind == "RESUME_AUTHORIZED"
            ]
        )
        == 1
    )
    with pytest.raises(ConflictError):
        list(
            resume_conversation(
                db,
                conversation_id,
                ResumeInput(plan_id="another-plan", idempotency_key=request.idempotency_key),
                provider=provider,
            )
        )


def test_resume_when_ui_already_executed_reuses_its_original_run(
    db: Database,
    dataset: DatasetView,
) -> None:
    """An existing user execution is reused even if its operation identity differs."""
    conversation_id, plan = pause_deletion(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    original = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    before = get_conversation(db, conversation_id)
    provider = FakeProvider([ModelResponse(content="Existing receipt confirmed.")])
    resumed = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="ui-executed"),
            provider=provider,
        )
    )
    receipt = next(
        event.outcome.run for event in resumed if event.event == "receipt" and event.outcome
    )
    assert receipt == original
    assert list_runs(db) == [original]
    assert get_conversation(db, conversation_id).messages[:-1] == before.messages
    assert (
        len([item for item in list_invocations(db, conversation_id) if item.name == "delete_files"])
        == 1
    )
    assert original.id in provider.requests[0].messages[-1].content


def test_new_message_when_interrupted_invalidates_gate_with_queryable_audit(
    db: Database,
    dataset: DatasetView,
) -> None:
    """A later user turn makes the old gate unusable while retaining its frozen plan history."""
    conversation_id, plan = pause_deletion(db, dataset.id)
    newer = list(
        send_message(
            db,
            conversation_id,
            MessageInput(content="Keep the files instead."),
            provider=FakeProvider([ModelResponse(content="Changed request acknowledged.")]),
        )
    )
    assert newer[-1].event == "done"
    invalidations = [
        entry for entry in list_audit(db, conversation_id) if entry.kind == "INTERRUPT_INVALIDATED"
    ]
    assert len(invalidations) == 1
    assert invalidations[0].plan_id == plan.id
    assert invalidations[0].reason
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    before = get_conversation(db, conversation_id)
    with pytest.raises(AuthorizationError):
        list(
            resume_conversation(
                db,
                conversation_id,
                ResumeInput(plan_id=plan.id, idempotency_key="invalidated"),
                provider=FakeProvider([]),
            )
        )
    assert get_conversation(db, conversation_id).messages == before.messages
    assert list_audit(db, conversation_id)[-1].kind == "RESUME_DENIED"
    assert list_runs(db) == []


def test_executor_when_approval_actor_differs_refuses_to_consume_forged_record(
    db: Database,
    dataset: DatasetView,
) -> None:
    """The underlying executor independently rejects another actor's stored approval."""
    _, plan = pause_deletion(db, dataset.id)
    forge_approval(db, plan, "actor_mismatch")
    with pytest.raises(AuthorizationError, match="actor"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with db.session() as session:
        approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id))
        assert approval is not None
        assert approval.consumed is False
    assert len(list_files(db, dataset.id)) == 2
    assert list_runs(db)[0].status == "DENIED"
