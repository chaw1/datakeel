# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise every structured-output mode using an injected synthetic HTTP peer."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import httpx
import pytest

from datakeel.core.errors import ProviderError
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.extraction_runtime.adapter import llm_extractor

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import TextBlock


_RESULT = {
    "entities": [{"name": "Cedar", "type": "Company"}, {"name": "Reed", "type": "Product"}],
    "relations": [
        {
            "head": "Cedar",
            "relation": "develops",
            "tail": "Reed",
            "evidence": "Cedar develops Reed.",
        }
    ],
}


def _profile(provider: str, method: str) -> ExtractionProfile:
    return ExtractionProfile.model_validate(
        {
            "id": "fixture",
            "extractor": "llm",
            "provider": provider,
            "model": "fixture-model",
            "base_url": "https://fixture.invalid/v1",
            "output_method": method,
            "max_output_tokens": 222,
            "request_parameters": {"thinking": {"type": "disabled"}}
            if provider == "anthropic"
            else {"enable_thinking": False, "num_ctx": 8192, "reasoning_effort": "none"},
        }
    )


def _response(provider: str, method: str, *, reason: str = "stop") -> dict[str, JsonValue]:
    if provider == "anthropic":
        content: list[JsonValue] = [{"type": "text", "text": json.dumps(_RESULT)}]
        if method == "function_calling":
            content = [
                {"type": "tool_use", "id": "call-1", "name": "KGExtraction", "input": _RESULT}
            ]
        return {
            "id": "msg-fixture",
            "type": "message",
            "role": "assistant",
            "model": "fixture-model",
            "content": content,
            "stop_reason": reason,
            "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
        }
    message: dict[str, JsonValue] = {"role": "assistant", "content": json.dumps(_RESULT)}
    if method == "function_calling":
        message["tool_calls"] = [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "KGExtraction", "arguments": json.dumps(_RESULT)},
            }
        ]
    return {
        "choices": [{"message": message, "finish_reason": reason}],
        "usage": {"prompt_tokens": 13, "completion_tokens": 5},
    }


def _assert_wire(payload: dict[str, JsonValue], provider: str, method: str) -> None:
    assert "Cedar develops Reed." in str(payload["messages"])
    assert "Company" in str(payload["messages"])
    assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 222
    if provider != "anthropic":
        assert payload["enable_thinking"] is False
        assert payload["num_ctx"] == 8192
        assert payload["reasoning_effort"] == "none"
    else:
        assert payload["thinking"] == {"type": "disabled"}
    if method == "function_calling":
        assert "KGExtraction" in str(payload["tool_choice"])
        assert "enum" in str(payload["tools"])
        assert "develops" in str(payload["tools"])
    elif method == "json_schema":
        declaration = (
            payload["response_format"] if provider != "anthropic" else payload["output_config"]
        )
        assert "enum" in str(declaration)
        assert "Company" in str(declaration)
        assert "develops" in str(declaration)
    elif provider != "anthropic":
        assert payload["response_format"] == {"type": "json_object"}
    else:
        assert "tools" not in payload


@pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama"])
@pytest.mark.parametrize("method", ["json_schema", "function_calling", "json_mode"])
def test_extract_when_structured_reply_preserves_claims_usage_and_wire_schema(
    schema: KGSchema, block: TextBlock, provider: str, method: str
) -> None:
    """Send schema enums and explicit settings while retaining typed response accounting."""

    def respond(request: httpx.Request) -> httpx.Response:
        _assert_wire(json.loads(request.content), provider, method)
        header = "authorization" if provider != "anthropic" else "x-api-key"
        assert "fixture-key" in request.headers[header]
        return httpx.Response(200, json=_response(provider, method))

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        llm_extractor(_profile(provider, method), "fixture-key", client) as extractor,
    ):
        result = extractor.extract(block, schema)
    assert result.output.model_dump(mode="json") == _RESULT
    assert (result.input_tokens, result.output_tokens) == (13, 5)


@pytest.mark.parametrize(
    ("provider", "reason"), [("openai", "length"), ("anthropic", "max_tokens")]
)
def test_extract_when_truncated_preserves_failure_reason_without_parsing_incomplete_json(
    schema: KGSchema, block: TextBlock, provider: str, reason: str
) -> None:
    """A length stop remains visible even when the returned content cannot be parsed."""
    payload = _response(provider, "json_mode", reason=reason)
    if provider != "anthropic":
        payload["choices"] = [
            {"message": {"content": "{", "role": "assistant"}, "finish_reason": reason}
        ]
    else:
        payload["content"] = [{"type": "text", "text": "{"}]
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        llm_extractor(_profile(provider, "json_mode"), "fixture-key", client) as extractor,
    ):
        result = extractor.extract(block, schema)
    assert result.finish_reason == reason
    assert result.output.relations == ()


@pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama"])
@pytest.mark.parametrize("include_usage", [False, True])
def test_extract_when_billing_absent_marks_usage_unknown(
    schema: KGSchema, block: TextBlock, provider: str, *, include_usage: bool
) -> None:
    """Do not turn absent or null observed usage into fictional zero-token billing."""
    payload = _response(provider, "json_mode")
    if include_usage:
        payload["usage"] = None
    else:
        del payload["usage"]
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        llm_extractor(_profile(provider, "json_mode"), "fixture-key", client) as extractor,
    ):
        result = extractor.extract(block, schema)
    assert (result.input_tokens, result.output_tokens) == (None, None)


@pytest.mark.parametrize(
    "message",
    [
        {"role": "assistant", "content": "not JSON"},
        {"role": "assistant", "content": '{"unexpected":true}'},
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": 42},
    ],
)
def test_extract_when_json_reply_invalid_reports_parse_error(
    schema: KGSchema, block: TextBlock, message: dict[str, JsonValue]
) -> None:
    """Reject malformed structured output without exposing provider response content."""
    payload = {"choices": [{"message": message, "finish_reason": "stop"}]}
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        llm_extractor(_profile("openai", "json_mode"), "fixture-key", client) as extractor,
        pytest.raises(ProviderError) as captured,
    ):
        extractor.extract(block, schema)
    assert captured.value.reason == "parse_error"


@pytest.mark.parametrize("variant", ["missing", "wrong_name", "malformed", "multiple"])
def test_extract_when_function_reply_invalid_reports_parse_error(
    schema: KGSchema,
    block: TextBlock,
    variant: Literal["missing", "wrong_name", "malformed", "multiple"],
) -> None:
    """Do not accept missing, mismatched, multiply emitted or unparsable structured calls."""
    call = {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "other" if variant == "wrong_name" else "KGExtraction",
            "arguments": "{" if variant == "malformed" else json.dumps(_RESULT),
        },
    }
    calls = [] if variant == "missing" else [call, call] if variant == "multiple" else [call]
    payload = {
        "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": calls}}]
    }
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        llm_extractor(_profile("openai", "function_calling"), "fixture-key", client) as extractor,
        pytest.raises(ProviderError) as captured,
    ):
        extractor.extract(block, schema)
    assert captured.value.reason == "parse_error"
