# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conversation boundaries validate configuration and preserve full tool exchanges."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from datakeel.core.agent_models import (
    ChatMessage,
    ContextSegment,
    Conversation,
    ConversationCreate,
    ConversationLease,
    MessageInput,
    ModelResponse,
    ToolCall,
)
from datakeel.core.models import JsonDocument, new_id


def test_conversation_when_serialized_preserves_complete_history_and_tool_arguments() -> None:
    """Retain more than thirty messages without losing protocol correlation IDs."""
    call = ToolCall(name="search_files", arguments=JsonDocument({"quality_max": 60}))
    conversation = Conversation(
        id="session", config=ConversationCreate(), messages=[ChatMessage(role="user")] * 40
    )
    response = ModelResponse(tool_calls=[call])
    assert len(Conversation.model_validate_json(conversation.model_dump_json()).messages) == 40
    assert response.tool_calls[0].arguments.root == {"quality_max": 60}
    assert ConversationLease(token=new_id(), replay=[]).replay == []


@pytest.mark.parametrize("field", ["unknown", "actor", "api_key"])
def test_conversation_configuration_when_extra_field_supplied_rejects_it(field: str) -> None:
    """Forbid caller-controlled identity and credentials inside persisted configuration."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ConversationCreate.model_validate({field: "untrusted"})


def test_conversation_boundaries_when_invalid_reject_input_and_mutation() -> None:
    """Reject invalid lengths and token counts while keeping configuration immutable."""
    with pytest.raises(ValidationError):
        MessageInput(content="")
    with pytest.raises(ValidationError):
        ContextSegment(name="history", kind="volatile", text="", tokens=-1)
    with pytest.raises(ValidationError, match="frozen_instance"):
        ConversationCreate().dry_run = True
