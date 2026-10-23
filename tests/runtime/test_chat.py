# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Scripted chat models preserve the provider-neutral fixture contract."""

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.core.agent_models import (
    ChatMessage,
    ContextSegment,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolDefinition,
)
from datakeel.core.errors import ValidationError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.runtime.chat import ScriptedChatModel, complete


def request() -> ModelRequest:
    """Keep named facts, complete tool exchanges, and segment ordering in the request."""
    call = ToolCall(id="prior-call", name="search_files", arguments=JsonDocument({"limit": 2}))
    return ModelRequest(
        model="fake-script",
        messages=[
            ChatMessage(role="system", content="Use controlled tools."),
            ChatMessage(role="user", content="Find files."),
            ChatMessage(role="assistant", tool_calls=[call]),
            ChatMessage(role="tool", tool_call_id=call.id, content="{}", name=call.name),
            ChatMessage(role="user", content="{}", name="workspace"),
        ],
        tools=[
            ToolDefinition(
                name="search_files",
                description="Search",
                parameters=JsonDocument({"type": "object"}),
            )
        ],
        segments=[ContextSegment(name="system", kind="stable", text="guidance", tokens=17)],
        max_output_tokens=55,
    )


def test_scripted_when_bound_preserves_request_segments_calls_and_exact_usage() -> None:
    """The shell delegates to the original script once and preserves authoritative usage."""
    response = ModelResponse(
        content="Next.",
        tool_calls=[ToolCall(id="next-call", name="search_files")],
        usage=TokenUsage(
            input_tokens=31, output_tokens=9, cache_read_tokens=7, cache_write_tokens=3
        ),
        stop_reason="tool_calls",
    )
    fixture = FakeProvider([response])
    result = complete(fixture, request())
    assert fixture.requests == [request()]
    assert result == response
    assert fixture.script == []


def test_scripted_when_usage_derived_matches_direct_fixture_algorithm() -> None:
    """Adding the chat shell does not change fake token estimation or message names."""
    response = ModelResponse(content="Derived fixture tokens.")
    original, wrapped = FakeProvider([response]), FakeProvider([response])
    assert complete(wrapped, request()) == original.complete(request())
    assert wrapped.requests == original.requests


def test_scripted_when_no_tools_still_calls_original_provider() -> None:
    """A final plain answer needs no tool declarations to preserve its usage."""
    fixture = FakeProvider([])
    result = complete(fixture, request().model_copy(update={"tools": []}))
    assert result.content == "Complete."
    assert result.usage.input_tokens == 17


def test_scripted_when_metadata_missing_rejects_unaccounted_model_invocation() -> None:
    """Direct framework calls cannot silently reconstruct different prompt accounting."""
    with pytest.raises(ValidationError, match="request metadata"):
        ScriptedChatModel(FakeProvider([])).invoke("unaccounted")
