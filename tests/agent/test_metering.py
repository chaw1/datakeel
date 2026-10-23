# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unknown usage remains conservatively billed after the chat-model translation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse
from datakeel.core.harness_models import TokenUsage
from datakeel.harness.service import list_traces

if TYPE_CHECKING:
    from datakeel.core.agent_models import ModelRequest
    from datakeel.storage.database import Database


class UnmeteredProvider:
    """Return a successful response whose provider omitted authoritative billing."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Keep absent usage distinct from actual zero-token usage."""
        return ModelResponse(content="Completed without usage metadata.", usage_known=False)


def test_model_when_usage_absent_retains_reservation_and_unknown_trace(db: Database) -> None:
    """The adapter must not turn missing usage into a free, actually billed completion."""
    conversation = create_conversation(db, ConversationCreate())
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="inspect"), provider=UnmeteredProvider()
        )
    )
    assert [event.event for event in events] == ["text", "done"]
    traces = list_traces(db, conversation.id)
    assert len(traces) == 1
    assert traces[0].billing_status == "unknown"
    assert traces[0].usage == TokenUsage()
    assert traces[0].accounted_tokens > 0
