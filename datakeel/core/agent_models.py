# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable conversation and model-provider boundaries without runtime dependencies."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field

from datakeel.core.harness_models import BudgetLimits, TokenUsage
from datakeel.core.models import BoundaryModel, JsonDocument, new_id, utcnow


class ToolCall(BoundaryModel):
    """One model-requested invocation with its protocol correlation identifier."""

    id: str = Field(default_factory=new_id)
    name: str
    arguments: JsonDocument = Field(default_factory=lambda: JsonDocument({}))


class ToolDefinition(BoundaryModel):
    """A discoverable, validated function declaration."""

    name: str
    description: str
    parameters: JsonDocument


class ChatMessage(BoundaryModel):
    """Persist text and complete tool exchanges without truncating history."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    tool_call_id: str | None = None
    name: str | None = None


class ContextSegment(BoundaryModel):
    """An ordered context component with explicit token accounting."""

    name: str
    kind: Literal["stable", "volatile"]
    text: str
    tokens: int = Field(ge=0)


class ModelRequest(BoundaryModel):
    """Provider-neutral model input including complete context accounting."""

    model: str
    messages: list[ChatMessage]
    tools: list[ToolDefinition]
    segments: list[ContextSegment]
    max_output_tokens: int = Field(default=1024, ge=1)


class ModelResponse(BoundaryModel):
    """Provider-neutral completion and authoritative billing usage."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    usage: TokenUsage = Field(default_factory=TokenUsage)
    stop_reason: str = "stop"


class Provider(Protocol):
    """Allow real protocol adapters and deterministic scripted replacements."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Produce one complete assistant response."""
        ...


class ConversationCreate(BoundaryModel):
    """Bound a local conversation before accepting its first message."""

    dataset_id: str | None = None
    provider: Literal["fake", "openai", "anthropic"] = "fake"
    model: str = "fake-demo"
    dry_run: bool = False
    budget: BudgetLimits = Field(default_factory=BudgetLimits)
    max_turns: int = Field(default=12, ge=1, le=100)
    max_output_tokens: int = Field(default=1024, ge=1, le=16384)


class MessageInput(BoundaryModel):
    """An idempotent user turn, independent of transport reconnects."""

    content: str = Field(min_length=1, max_length=80000)
    idempotency_key: str = Field(default_factory=new_id, min_length=1, max_length=200)


class Conversation(BoundaryModel):
    """The durable within-session history and its configuration."""

    id: str
    actor: Literal["local"] = "local"
    config: ConversationCreate
    created_at: datetime = Field(default_factory=utcnow)
    messages: list[ChatMessage] = Field(default_factory=list[ChatMessage])
    events: list[JsonDocument] = Field(default_factory=list[JsonDocument])
    turns: int = 0


class ConversationLease(BoundaryModel):
    """Authorize a single writer while retaining replayable completed requests."""

    token: str
    replay: list[JsonDocument] | None = None
