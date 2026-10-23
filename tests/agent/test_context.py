# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stable prefixes precede complete volatile history and exact usage attribution."""

from datakeel.agent.context import allocate_tokens, assemble, estimate_tokens
from datakeel.agent.tools import resident_tools
from datakeel.core.agent_models import ChatMessage, Conversation, ConversationCreate
from datakeel.core.models import JsonDocument


def test_context_when_history_changes_retains_stable_prefix_and_all_messages() -> None:
    """Keep stable schema bytes identical while appending forty historical messages."""
    conversation = Conversation(id="session", config=ConversationCreate())
    first = assemble(conversation, resident_tools(), [], JsonDocument({"dataset_id": "first"}))
    changed = conversation.model_copy(
        update={"messages": [ChatMessage(role="user", content=str(index)) for index in range(40)]}
    )
    second = assemble(changed, resident_tools(), [], JsonDocument({"dataset_id": "second"}))
    assert first.segments[:2] == second.segments[:2]
    assert all(segment.kind == "volatile" for segment in second.segments[2:])
    assert len(second.messages) == 42
    assert second.messages[-1].name == "workspace_context"
    assert estimate_tokens("中文") == len("中文".encode())
    assert estimate_tokens("") == 1


def test_context_when_usage_reported_reconciles_integer_segments_exactly() -> None:
    """Allocate small and large provider token totals without rounding drift."""
    conversation = Conversation(id="session", config=ConversationCreate())
    request = assemble(conversation, resident_tools(), [], JsonDocument({}))
    for total in (0, 1, 37, 10001):
        attributed = allocate_tokens(request.segments, total)
        assert sum(segment.tokens for segment in attributed) == total
        assert [segment.stable for segment in attributed] == [True, True, False, False, False]
