# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect leaked replies before transcript, graph checkpoints or tools can observe them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.harness.service import list_traces
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.mark.parametrize("channel", ["text", "arguments"])
def test_canary_leak_stops_before_persistence_or_tools(
    db: Database, channel: Literal["text", "arguments"]
) -> None:
    """One leaked response is charged but its text and calls never enter observable history."""
    conversation = create_conversation(db, ConversationCreate())
    canary = get_canary(db, conversation.id)
    response = ModelResponse(
        content=canary if channel == "text" else "Do not publish even this harmless text.",
        tool_calls=[
            ToolCall(
                name="list_datasets",
                arguments=JsonDocument({"note": canary} if channel == "arguments" else {}),
            )
        ],
    )
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="Analyze"), provider=FakeProvider([response])
        )
    )
    assert [event.event for event in events] == ["stopped", "done"]
    assert events[0].stop_reason == "canary_leak"
    assert list_invocations(db) == []
    assert len(list_traces(db, conversation.id)) == 1
    audit = list_audit(db, conversation.id)
    assert len(audit) == 1
    assert audit[0].kind == "CANARY_LEAK"
    view = get_conversation(db, conversation.id)
    assert [message.role for message in view.messages] == ["user"]
    assert canary not in view.model_dump_json()
    assert canary not in audit[0].model_dump_json()
    for record in list_checkpoints(db, CheckpointQuery(thread_id=conversation.id)):
        assert canary.encode() not in record.checkpoint + record.metadata
        assert all(canary.encode() not in write.value for write in record.writes)


def test_prefix_only_reply_is_not_blocked_and_canary_is_after_stable_prefix(db: Database) -> None:
    """A safe response may name the sentinel prefix without revealing the private value."""
    conversation = create_conversation(db, ConversationCreate())
    fake = FakeProvider([ModelResponse(content="dkc_ is only a prefix.")])
    events = list(send_message(db, conversation.id, MessageInput(content="Analyze"), provider=fake))
    assert [event.event for event in events] == ["text", "done"]
    assert list_audit(db, conversation.id) == []
    assert [part.name for part in fake.requests[0].segments[:3]] == [
        "instructions",
        "core_tools",
        "canary",
    ]
    assert fake.requests[0].segments[2].kind == "volatile"
    assert fake.requests[0].segments[2].tokens <= 96


def test_canary_guard_cannot_be_disabled(db: Database) -> None:
    """Provide one non-parametrized assertion target for the leak-guard mutant."""
    test_canary_leak_stops_before_persistence_or_tools(db, "text")
