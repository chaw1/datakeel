# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Model attempts attribute memory separately and never cache deleted prompt content."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.memory_models import MemoryCreate
from datakeel.harness.service import list_traces
from datakeel.memory.service import create_memory, delete_memory, get_memory, list_memories

if TYPE_CHECKING:
    from datakeel.core.agent_models import ModelRequest
    from datakeel.storage.database import Database


class FailingProvider(FakeProvider):
    """Capture an actual attempted request before returning an expected provider failure."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Record the prompt so a failed attempt still has inspectable use evidence."""
        super().complete(request)
        msg = "Generated provider failure"
        raise ValueError(msg)


class DeletingProvider(FakeProvider):
    """Delete an entry after its prompt was sent, before model-use reinforcement runs."""

    def __init__(self, db: Database, memory_id: str) -> None:
        """Arrange an interleaving with an additional model node in the same response."""
        super().__init__(
            [
                ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
                ModelResponse(content="Done"),
            ]
        )
        self.db, self.memory_id = db, memory_id

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Represent deletion committed while the provider processes the selected prompt."""
        if not self.requests:
            delete_memory(self.db, self.memory_id)
        return super().complete(request)


def test_memory_when_used_across_conversations_has_segment_trace_and_identity_only_events(
    db: Database,
) -> None:
    """Each fresh conversation selects from authoritative facts and accounts memory separately."""
    source = create_conversation(db, ConversationCreate())
    entry = create_memory(
        db,
        MemoryCreate(
            content="revenue metric excludes generated refund rows",
            source_conversation_id=source.id,
        ),
    )
    for _ in range(2):
        conversation = create_conversation(db, ConversationCreate())
        provider = FakeProvider([ModelResponse(content="I reviewed the stored guidance.")])
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Explain revenue metric"),
                provider=provider,
            )
        )
        request = provider.requests[0]
        names = [segment.name for segment in request.segments]
        assert names.index("memory") < names.index("history") < names.index("workspace")
        assert request.messages[-1].name == "workspace_context"
        assert any(entry.content in segment.text for segment in request.segments)
        assert events[-1].used_memory_ids == [entry.id]
        assert entry.content not in events[-1].model_dump_json()
        trace = list_traces(db, conversation.id)[0]
        assert next(segment for segment in trace.segments if segment.name == "memory").tokens > 0
        assert sum(segment.tokens for segment in trace.segments) == trace.usage.input_tokens
    assert get_memory(db, entry.id).strength > 1.99


def test_memory_when_budget_rejected_before_model_does_not_strengthen_or_record_use(
    db: Database,
) -> None:
    """Selecting a context is not a use until the budget permits a provider attempt."""
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"))
    conversation = create_conversation(
        db, ConversationCreate(budget=BudgetLimits(conversation_tokens=1))
    )
    provider = FakeProvider([ModelResponse(content="This response must not be consumed.")])
    events = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert provider.requests == []
    assert events[-2].stop_reason == "budget_exceeded"
    assert events[-1].used_memory_ids == []
    assert get_memory(db, entry.id).strength == 1
    assert get_memory(db, entry.id).last_used_at is None


def test_memory_when_provider_fails_after_attempt_still_strengthens_and_reports_ids(
    db: Database,
) -> None:
    """A failed provider received the memory and must retain use and accounting evidence."""
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"))
    conversation = create_conversation(db, ConversationCreate())
    provider = FailingProvider([])
    events = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert len(provider.requests) == 1
    assert events[-2].stop_reason == "provider_error"
    assert events[-1].used_memory_ids == [entry.id]
    assert get_memory(db, entry.id).strength > 1.49
    assert get_memory(db, entry.id).last_used_at is not None
    assert len(list_traces(db, conversation.id)) == 1


def test_memory_when_deleted_between_messages_rechecks_same_conversation_facts(
    db: Database,
) -> None:
    """A later model node never reconstructs memory text from a historical ID-only event."""
    entry = create_memory(db, MemoryCreate(content="revenue metric generated retention guidance"))
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider(
        [ModelResponse(content="Reviewed."), ModelResponse(content="Reviewed.")]
    )
    first = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert first[-1].used_memory_ids == [entry.id]
    delete_memory(db, entry.id)
    second = list(
        send_message(
            db, conversation.id, MessageInput(content="revenue metric again"), provider=provider
        )
    )
    assert second[-1].used_memory_ids == []
    assert entry.content not in provider.requests[-1].model_dump_json()
    assert not any(segment.name == "memory" for segment in provider.requests[-1].segments)


def test_memory_when_deleted_during_model_call_never_resurrects_on_reinforcement(
    db: Database,
) -> None:
    """An in-flight prompt is historical use; the next model node sees the committed deletion."""
    entry = create_memory(db, MemoryCreate(content="revenue metric generated retention guidance"))
    conversation = create_conversation(db, ConversationCreate())
    provider = DeletingProvider(db, entry.id)
    events = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert len(provider.requests) == 2
    assert any(segment.name == "memory" for segment in provider.requests[0].segments)
    assert not any(segment.name == "memory" for segment in provider.requests[1].segments)
    assert list_memories(db, include_archived=True) == []
    assert events[-1].used_memory_ids == [entry.id]
