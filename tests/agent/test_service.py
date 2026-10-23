# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conversation service drives real controlled actions through scripted model exchanges."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import (
    create_conversation,
    get_conversation,
    list_conversations,
    send_message,
)
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.storage.dataset_service import list_files
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def action_script(dataset_id: str, action: str = "quarantine_files") -> list[ModelResponse]:
    """Discover the action schema before requesting a frozen low-quality selection."""
    return [
        ModelResponse(
            tool_calls=[ToolCall(name="tool_search", arguments=JsonDocument({"query": action}))]
        ),
        ModelResponse(
            tool_calls=[
                ToolCall(
                    name=action,
                    arguments=JsonDocument(
                        {"selection": {"dataset_id": dataset_id, "quality_max": 0}}
                    ),
                )
            ]
        ),
        ModelResponse(content="Finished with a recorded receipt."),
    ]


def test_reversible_conversation_when_run_emits_plan_receipt_and_durable_audit(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Execute a reversible selection automatically and retain attributed receipt events."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Quarantine low quality"),
            provider=FakeProvider(action_script(dataset.id)),
        )
    )
    assert [event.event for event in events] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "plan",
        "receipt",
        "text",
        "done",
    ]
    assert sum(bool(file.metadata.get("quarantined")) for file in list_files(db, dataset.id)) == 1
    assert list_runs(db)[0].receipt is not None
    assert (
        list_runs(db)[0].receipt.on_behalf_of == f"agent:datakeel-agent/session:{conversation.id}"
    )
    assert all(item.session_id == conversation.id for item in list_invocations(db))
    assert list_conversations(db)[0].id == conversation.id


def test_irreversible_conversation_when_ui_approves_hydrates_latest_run_on_reload(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Pause at a full plan and expose the user-approved execution after reloading."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Delete selected files"),
            provider=FakeProvider(action_script(dataset.id, "delete_files")),
        )
    )
    plan = next(event.outcome.plan for event in events if event.event == "plan" and event.outcome)
    assert plan is not None
    assert events[-2].stop_reason == "approval_required"
    assert list_runs(db) == []
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    loaded = get_conversation(db, conversation.id)
    current = next(event.outcome for event in loaded.events if event.event == "plan")
    assert current is not None
    assert current.plan is not None
    assert current.run is not None
    assert current.plan.status == "EXECUTED"
    assert current.run.receipt is not None


def test_dry_run_when_reversible_action_requested_prepares_without_mutation(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Apply dry-run to reversible actions as strictly as to irreversible actions."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id, dry_run=True))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Preview quarantine"),
            provider=FakeProvider(action_script(dataset.id)),
        )
    )
    assert events[-2].stop_reason == "dry_run"
    assert not any(file.metadata.get("quarantined") for file in list_files(db, dataset.id))
    assert list_runs(db) == []


def test_completed_message_when_replayed_does_not_repeat_tools_or_transcript(db: Database) -> None:
    """Replay identical persisted event IDs without calling a second provider."""
    conversation = create_conversation(db, ConversationCreate())
    request = MessageInput(content="List assets")
    provider = FakeProvider([ModelResponse(content="No action required.")])
    first = list(send_message(db, conversation.id, request, provider=provider))
    second = list(send_message(db, conversation.id, request, provider=provider))
    assert first == second
    assert len(provider.requests) == 1
    assert len(get_conversation(db, conversation.id).messages) == 2


def test_interrupted_stream_when_recovered_closes_pending_tool_protocol(db: Database) -> None:
    """Keep a closed stream replayable through GET without leaving unmatched tool calls."""
    conversation = create_conversation(db, ConversationCreate())
    request = MessageInput(content="List assets")
    provider = FakeProvider([ModelResponse(tool_calls=[ToolCall(name="list_datasets")])])
    stream = send_message(db, conversation.id, request, provider=provider)
    assert next(stream).event == "tool_call"
    stream.close()
    loaded = get_conversation(db, conversation.id)
    assert loaded.events[-2].stop_reason == "interrupted"
    assert loaded.messages[-1].role == "tool"
    with pytest.raises(ConflictError, match="interrupted"):
        list(send_message(db, conversation.id, request, provider=provider))
    assert (
        list(
            send_message(
                db, conversation.id, MessageInput(content="Continue"), provider=FakeProvider([])
            )
        )[-1].event
        == "done"
    )
