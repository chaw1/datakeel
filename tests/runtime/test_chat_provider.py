# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider wire protocols remain deterministic without accessing external services."""

from __future__ import annotations

import gzip
import json
from typing import TYPE_CHECKING, Literal

import httpx
import pytest

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    ChatMessage,
    ContextSegment,
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ToolCall,
    ToolDefinition,
)
from datakeel.core.errors import ValidationError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.core.settings import Settings
from datakeel.harness.service import list_traces
from datakeel.runtime.chat_provider import model_provider

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database


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
        assert json.loads(payload["messages"][2]["tool_calls"][0]["function"]["arguments"]) == {
            "quality_max": 60
        }
        assert payload["messages"][3]["tool_call_id"] == "call-1"
        assert payload["tools"][0]["function"]["parameters"] == {"type": "object"}
        assert payload["max_completion_tokens"] == 100
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-2",
                                    "type": "function",
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

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        model_provider(
            ConversationCreate(provider="openai"),
            Settings.model_validate(
                {"openai_api_key": "fixture-key", "openai_base_url": "https://fixture.invalid/v1"}
            ),
            client,
        ) as provider,
    ):
        result = provider.complete(model_request)
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
                "id": "msg-fixture",
                "type": "message",
                "role": "assistant",
                "model": "fixture-model",
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

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        model_provider(
            ConversationCreate(provider="anthropic"),
            Settings.model_validate(
                {
                    "anthropic_api_key": "fixture-key",
                    "anthropic_base_url": "https://fixture.invalid",
                }
            ),
            client,
        ) as provider,
    ):
        result = provider.complete(model_request)
    assert result.content == "Checking."
    assert result.tool_calls[0].id == "call-2"
    assert result.usage == TokenUsage(
        input_tokens=30, output_tokens=8, cache_read_tokens=10, cache_write_tokens=5
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": "invalid"},
        {"choices": [True]},
        {"choices": [{"message": {"role": "assistant", "content": 1}}]},
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "invalid-call",
                                "type": "function",
                                "function": {"name": "search_files", "arguments": "not-json"},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        },
        {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": True, "completion_tokens": 1},
        },
    ],
)
def test_openai_when_response_shape_invalid_rejects_provider_data(
    model_request: ModelRequest, payload: dict[str, JsonValue]
) -> None:
    """Reject malformed provider objects before they enter durable memory."""
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            trust_env=False,
        ) as client,
        model_provider(
            ConversationCreate(provider="openai"),
            Settings.model_validate({"openai_api_key": "fixture"}),
            client,
        ) as provider,
        pytest.raises(ValidationError, match="Model provider"),
    ):
        provider.complete(model_request)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_provider_when_http_fails_propagates_error_without_fabricating_completion(
    model_request: ModelRequest, kind: Literal["openai", "anthropic"]
) -> None:
    """Keep failed network attempts distinct from successful model output."""
    attempts: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(
            429, json={"error": {"message": "limited", "type": "rate_limit_error"}}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(fail), trust_env=False) as client,
        model_provider(
            ConversationCreate(provider=kind),
            Settings.model_validate({f"{kind}_api_key": "fixture"}),
            client,
        ) as provider,
        pytest.raises(ValidationError, match="Model provider"),
    ):
        provider.complete(model_request)
    assert len(attempts) == 1


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("include_usage", [False, True])
def test_provider_when_usage_missing_or_null_marks_billing_unknown(
    model_request: ModelRequest, kind: Literal["openai", "anthropic"], *, include_usage: bool
) -> None:
    """Missing SDK billing fields never become fabricated actual zero-token usage."""
    payload: dict[str, JsonValue] = (
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Done."}, "finish_reason": "stop"}
            ]
        }
        if kind == "openai"
        else {
            "id": "msg-fixture",
            "type": "message",
            "role": "assistant",
            "model": "fixture-model",
            "content": [{"type": "text", "text": "Done."}],
            "stop_reason": "end_turn",
        }
    )
    if include_usage:
        payload["usage"] = None
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            trust_env=False,
        ) as client,
        model_provider(
            ConversationCreate(provider=kind),
            Settings.model_validate({f"{kind}_api_key": "fixture"}),
            client,
        ) as provider,
    ):
        result = provider.complete(model_request)
    assert result.content == "Done."
    assert result.usage == TokenUsage()
    assert result.usage_known is False


@pytest.mark.parametrize(
    ("kind", "settings_data", "expected"),
    [
        (
            "openai",
            {"openai_url": "https://fixture.invalid/compat/v1/chat/completions"},
            "https://fixture.invalid/compat/v1/chat/completions",
        ),
        (
            "anthropic",
            {"anthropic_url": "https://fixture.invalid/compat/v1/messages"},
            "https://fixture.invalid/compat/v1/messages",
        ),
        (
            "openai",
            {
                "openai_base_url": "https://fixture.invalid/new/v1/",
                "openai_url": "https://unused.invalid/custom",
            },
            "https://fixture.invalid/new/v1/chat/completions",
        ),
        (
            "anthropic",
            {
                "anthropic_base_url": "https://fixture.invalid/new/",
                "anthropic_url": "https://unused.invalid/custom",
            },
            "https://fixture.invalid/new/v1/messages",
        ),
    ],
)
def test_provider_when_endpoint_configured_uses_base_url_or_standard_legacy_path(
    model_request: ModelRequest,
    kind: Literal["openai", "anthropic"],
    settings_data: dict[str, str],
    expected: str,
) -> None:
    """Compatible services use the configured prefix while the SDK owns endpoint paths."""
    urls: list[str] = []

    def fail(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(500, json={"error": {"message": "fixture stop"}})

    with (
        httpx.Client(transport=httpx.MockTransport(fail), trust_env=False) as client,
        model_provider(
            ConversationCreate(provider=kind),
            Settings.model_validate({**settings_data, f"{kind}_api_key": "fixture"}),
            client,
        ) as provider,
        pytest.raises(ValidationError),
    ):
        provider.complete(model_request)
    assert urls == [expected]


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_provider_when_legacy_url_nonstandard_requires_explicit_base_url(
    kind: Literal["openai", "anthropic"],
) -> None:
    """Reject ambiguous deprecated endpoints locally before opening a connection."""
    with (
        httpx.Client(trust_env=False) as client,
        pytest.raises(ValidationError, match="BASE_URL"),
        model_provider(
            ConversationCreate(provider=kind),
            Settings.model_validate(
                {f"{kind}_api_key": "fixture", f"{kind}_url": "https://fixture.invalid/custom"}
            ),
            client,
        ),
    ):
        pytest.fail("Ambiguous endpoint unexpectedly accepted")


def test_provider_when_key_missing_rejects_direct_runtime_configuration() -> None:
    """The runtime boundary cannot construct an authenticated model without a key."""
    with (
        httpx.Client(trust_env=False) as client,
        pytest.raises(ValidationError, match="No API key"),
        model_provider(
            ConversationCreate(provider="openai"),
            Settings.model_validate({"openai_api_key": None}),
            client,
        ),
    ):
        pytest.fail("Missing key unexpectedly accepted")


def test_provider_when_usage_absent_preserves_conservative_reservation_in_trace(
    db: Database,
) -> None:
    """A successful text answer without usage retains its reserved token and cost bound."""
    config = ConversationCreate(provider="openai", model="gpt-4.1-mini", max_output_tokens=30)
    conversation = create_conversation(db, config)
    payload = {
        "choices": [{"message": {"role": "assistant", "content": "Done."}, "finish_reason": "stop"}]
    }
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            trust_env=False,
        ) as client,
        model_provider(
            config, Settings.model_validate({"openai_api_key": "fixture"}), client
        ) as provider,
    ):
        events = list(
            send_message(
                db, conversation.id, MessageInput(content="List available data."), provider=provider
            )
        )
    assert any(event.event == "text" and event.text == "Done." for event in events)
    traces = list_traces(db, conversation.id)
    assert len(traces) == 1
    trace = traces[0]
    assert trace.billing_status == "unknown"
    assert trace.usage == TokenUsage()
    assert trace.accounted_tokens > config.max_output_tokens
    assert trace.cost_usd > 0


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_provider_when_response_gzip_encoded_sdk_parses_decoded_body_once(
    model_request: ModelRequest,
    kind: Literal["openai", "anthropic"],
) -> None:
    """Compressed responses survive the bridge with decoded bytes and corrected headers."""
    payload = (
        {"choices": [{"message": {"role": "assistant", "content": "Done."}}]}
        if kind == "openai"
        else {
            "id": "message-fixture",
            "type": "message",
            "role": "assistant",
            "model": "fixture-model",
            "content": [{"type": "text", "text": "Done."}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 1},
        }
    )
    body = gzip.compress(json.dumps(payload).encode())
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    content=body,
                    headers={"content-encoding": "gzip", "content-length": str(len(body))},
                )
            )
        ) as client,
        model_provider(
            ConversationCreate(provider=kind),
            Settings.model_validate({f"{kind}_api_key": "fixture"}),
            client,
        ) as provider,
    ):
        result = provider.complete(model_request)
    assert result.content == "Done."
