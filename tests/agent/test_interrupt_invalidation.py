# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Accepted new messages invalidate old approval gates before model configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ActionPlan, ApprovalDecision
from datakeel.actions.service import approve_plan, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import (
    create_conversation,
    get_conversation,
    resume_conversation,
    send_message,
)
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ResumeInput
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.settings import Settings
from datakeel.runtime.graph import AgentGraph
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.dataset_service import list_files
from tests.agent.test_service import action_script

if TYPE_CHECKING:
    from datakeel.agent.models import AgentEvent
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def pause(db: Database, dataset_id: str) -> tuple[str, MessageInput, ActionPlan, list[AgentEvent]]:
    """Use a supplied offline script with an otherwise unconfigured vendor conversation."""
    conversation = create_conversation(
        db, ConversationCreate(dataset_id=dataset_id, provider="openai", model="gpt-4.1-mini")
    )
    request = MessageInput(content="Delete empty files", idempotency_key="pause-request")
    streamed = list(
        send_message(
            db,
            conversation.id,
            request,
            provider=FakeProvider(action_script(dataset_id, "delete_files")),
        )
    )
    plan = next(event.outcome.plan for event in streamed if event.event == "plan" and event.outcome)
    assert plan is not None
    assert streamed[-2].stop_reason == "approval_required"
    return conversation.id, request, plan, streamed


def missing_settings() -> Settings:
    """Resolve absent credentials deterministically without reading private credentials."""
    return Settings.model_validate({"openai_api_key": None})


@pytest.mark.parametrize("missing_key", [True, False])
def test_new_message_when_provider_setup_fails_invalidates_old_gate_before_configuration(
    db: Database,
    dataset: DatasetView,
    monkeypatch: pytest.MonkeyPatch,
    *,
    missing_key: bool,
) -> None:
    """A recorded replacement request cannot leave an earlier destructive plan resumable."""
    conversation_id, _, plan, _ = pause(db, dataset.id)
    settings = Settings.model_validate(
        {
            "openai_api_key": None if missing_key else "synthetic-fixture",
            "openai_base_url": None,
            "openai_url": "https://fixture.invalid/nonstandard",
        }
    )
    monkeypatch.setattr("datakeel.agent.factory.get_settings", lambda: settings)
    newer = list(send_message(db, conversation_id, MessageInput(content="Keep the files instead.")))
    assert [event.event for event in newer] == ["stopped", "done"]
    assert newer[0].stop_reason == "configuration_error"
    invalidated = list_audit(db, conversation_id)
    assert len(invalidated) == 1
    assert invalidated[0].kind == "INTERRUPT_INVALIDATED"
    assert invalidated[0].plan_id == plan.id
    assert invalidated[0].reason == "new_message"
    assert get_conversation(db, conversation_id).messages[-1].content == "Keep the files instead."
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    with pytest.raises(AuthorizationError, match="plan_not_pending"):
        list(
            resume_conversation(
                db,
                conversation_id,
                ResumeInput(plan_id=plan.id, idempotency_key="after-replacement"),
                provider=FakeProvider([]),
            )
        )
    assert list_audit(db, conversation_id)[-1].kind == "RESUME_DENIED"
    assert list_runs(db) == []
    assert len(list_files(db, dataset.id)) == 2


def test_message_replay_when_provider_configuration_missing_preserves_pending_gate(
    db: Database,
    dataset: DatasetView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replaying an accepted message neither rebuilds its provider nor invalidates its pause."""
    conversation_id, request, plan, original = pause(db, dataset.id)
    monkeypatch.setattr("datakeel.agent.factory.get_settings", missing_settings)
    assert list(send_message(db, conversation_id, request)) == original
    assert list_audit(db, conversation_id) == []
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    resumed = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="after-replay"),
            provider=FakeProvider([ModelResponse(content="Recovered.")]),
        )
    )
    assert [event.event for event in resumed] == ["receipt", "text", "done"]
    assert len(list_runs(db)) == 1


def test_resume_when_provider_configuration_fails_preserves_gate_for_later_request(
    db: Database,
    dataset: DatasetView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed recovery setup has no replacement user intent and cannot cancel the old gate."""
    conversation_id, _, plan, _ = pause(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    before = get_conversation(db, conversation_id).messages
    monkeypatch.setattr("datakeel.agent.factory.get_settings", missing_settings)
    failed = list(
        resume_conversation(
            db, conversation_id, ResumeInput(plan_id=plan.id, idempotency_key="bad-settings")
        )
    )
    assert failed[0].stop_reason == "configuration_error"
    assert [item.kind for item in list_audit(db, conversation_id)] == ["RESUME_AUTHORIZED"]
    assert get_conversation(db, conversation_id).messages == before
    assert list_runs(db) == []
    successful = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="fixed-settings"),
            provider=FakeProvider([ModelResponse(content="Recovered.")]),
        )
    )
    assert [event.event for event in successful] == ["receipt", "text", "done"]
    assert len(list_runs(db)) == 1
    assert [item.kind for item in list_audit(db, conversation_id)] == [
        "RESUME_AUTHORIZED",
        "RESUME_AUTHORIZED",
    ]


def test_unsigned_resume_with_missing_provider_configuration_is_denied_and_audited(
    db: Database,
    dataset: DatasetView,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider configuration cannot bypass approval rejection and its durable audit."""
    conversation_id, _, plan, _ = pause(db, dataset.id)
    monkeypatch.setattr("datakeel.agent.factory.get_settings", missing_settings)
    with pytest.raises(AuthorizationError, match="no_approval"):
        list(
            resume_conversation(
                db, conversation_id, ResumeInput(plan_id=plan.id, idempotency_key="unsigned")
            )
        )
    audit = list_audit(db, conversation_id)
    assert len(audit) == 1
    assert audit[0].kind == "RESUME_DENIED"
    assert audit[0].plan_id == plan.id
    assert audit[0].reason == "no_approval"
    assert list_runs(db) == []
    assert len(list_files(db, dataset.id)) == 2


def test_graph_without_configured_provider_rejects_model_execution(db: Database) -> None:
    """An inspection-only graph may invalidate checkpoints but cannot invoke a model."""
    conversation = create_conversation(db, ConversationCreate())
    graph = AgentGraph(db, conversation.id, "unused-token", None)
    with pytest.raises(ValidationError, match="configured provider"):
        list(graph.run())
