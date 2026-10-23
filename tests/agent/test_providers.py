# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider wire protocols remain deterministic without accessing external services."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.agent.providers import AnthropicProvider, FakeProvider, OpenAIProvider
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

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.fixture
def model_request() -> ModelRequest:
    """Represent a complete prior call/result pair plus stable system guidance."""
    call = ToolCall(id="call-1", name="search_files", arguments=JsonDocument({"quality_max": 60}))
    return ModelRequest(
        model="fixture-model",
        messages=[
            ChatMessage(role="system", content="Use controlled tools."),
            ChatMessage(role="user", content="Find low quality files."),
            ChatMessage(role="assistant", content="Searching.", tool_calls=[call]),
            ChatMessage(role="tool", content='{"matches": []}', tool_call_id=call.id),
        ],
        tools=[
            ToolDefinition(
                name="search_files",
                description="Find selected files.",
                parameters=JsonDocument({"type": "object"}),
            )
        ],
        segments=[ContextSegment(name="system", kind="stable", text="guidance", tokens=10)],
        max_output_tokens=100,
    )


def test_openai_when_tool_roundtrip_preserves_arguments_usage_and_headers(
    model_request: ModelRequest,
) -> None:
    """Preserve Chat Completions tool IDs and both cache billing categories."""

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer fixture-key"
        assert payload["messages"][2]["tool_calls"][0]["function"]["arguments"] == (
            '{"quality_max":60}'
        )
        assert payload["messages"][3]["tool_call_id"] == "call-1"
        assert payload["tools"][0]["function"]["parameters"] == {"type": "object"}
        assert payload["max_completion_tokens"] == 100
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-2",
                                    "function": {"name": "get_quality", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 30,
                    "completion_tokens": 8,
                    "prompt_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 5},
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = OpenAIProvider(
            client, api_key="fixture-key", url="https://fixture.invalid"
        ).complete(model_request)
    assert result.tool_calls[0].name == "get_quality"
    assert result.usage == TokenUsage(
        input_tokens=30, output_tokens=8, cache_read_tokens=10, cache_write_tokens=5
    )
    assert result.stop_reason == "tool_calls"


def test_anthropic_when_tool_roundtrip_uses_messages_blocks_and_inclusive_usage(
    model_request: ModelRequest,
) -> None:
    """Convert tool results to user blocks and include cache counts in total input."""

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["x-api-key"] == "fixture-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert payload["system"] == "Use controlled tools."
        assert payload["messages"][1]["content"][1]["type"] == "tool_use"
        assert payload["messages"][2]["role"] == "user"
        assert payload["messages"][2]["content"][0]["tool_use_id"] == "call-1"
        assert payload["tools"][0]["input_schema"] == {"type": "object"}
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "Checking."},
                    {"type": "tool_use", "id": "call-2", "name": "get_quality", "input": {}},
                ],
                "usage": {
                    "input_tokens": 15,
                    "output_tokens": 8,
                    "cache_read_input_tokens": 10,
                    "cache_creation_input_tokens": 5,
                },
                "stop_reason": "tool_use",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        provider = AnthropicProvider(client, api_key="fixture-key", url="https://fixture.invalid")
        result = provider.complete(model_request)
    assert result.content == "Checking."
    assert result.tool_calls[0].id == "call-2"
    assert result.usage.input_tokens == 30


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": "invalid"},
        {"choices": [True]},
        {"choices": [{"message": {"content": 1}}]},
        {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": True, "completion_tokens": 1},
        },
    ],
)
def test_openai_when_response_shape_invalid_rejects_provider_data(
    model_request: ModelRequest, payload: dict[str, JsonValue]
) -> None:
    """Reject malformed provider objects before they enter durable memory."""
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        provider = OpenAIProvider(client, api_key="fixture", url="https://fixture.invalid")
        with pytest.raises(ValidationError, match="Provider returned"):
            provider.complete(model_request)


@pytest.mark.parametrize("provider_type", [OpenAIProvider, AnthropicProvider])
def test_provider_when_http_fails_propagates_error_without_fabricating_completion(
    model_request: ModelRequest, provider_type: type[OpenAIProvider | AnthropicProvider]
) -> None:
    """Keep failed network attempts distinct from successful model output."""
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, json={"error": "limited"}))
    ) as client:
        provider = provider_type(client, api_key="fixture", url="https://fixture.invalid")
        with pytest.raises(httpx.HTTPStatusError):
            provider.complete(model_request)


def test_fake_when_script_consumed_retains_requests_and_derives_fixture_tokens(
    model_request: ModelRequest,
) -> None:
    """Allow deterministic replay with explicit or derived provider usage."""
    specified = ModelResponse(content="Measured", usage=TokenUsage(input_tokens=5, output_tokens=2))
    provider = FakeProvider([specified, ModelResponse(content="Derived")])
    assert provider.complete(model_request) == specified
    assert provider.complete(model_request).usage.input_tokens == 10
    assert provider.complete(model_request).content == "Complete."
    assert provider.requests == [model_request] * 3
