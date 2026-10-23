# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTPX adapters for Chat Completions and Messages tool protocols."""

import json

import httpx
from pydantic import JsonValue

from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, ToolCall
from datakeel.core.errors import ValidationError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        msg = "Provider returned an invalid object"
        raise ValidationError(msg)
    return value


def _items(value: JsonValue) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        msg = "Provider returned an invalid array"
        raise ValidationError(msg)
    return [_object(item) for item in value]


def _number(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = "Provider returned invalid token usage"
        raise ValidationError(msg)
    return value


def _text(value: JsonValue) -> str:
    if not isinstance(value, str):
        msg = "Provider returned invalid text"
        raise ValidationError(msg)
    return value


def _openai_message(message: ChatMessage) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments.model_dump_json()},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    return result


def _openai_result(data: JsonDocument) -> ModelResponse:
    choices = _items(data.root.get("choices", []))
    if not choices:
        msg = "Provider returned no completion choices"
        raise ValidationError(msg)
    message = _object(choices[0].get("message"))
    calls: list[ToolCall] = []
    for item in _items(message.get("tool_calls") or []):
        function = _object(item.get("function"))
        calls.append(
            ToolCall(
                id=_text(item.get("id")),
                name=_text(function.get("name")),
                arguments=JsonDocument.model_validate_json(_text(function.get("arguments"))),
            )
        )
    usage = _object(data.root.get("usage"))
    details = _object(usage.get("prompt_tokens_details") or {})
    return ModelResponse(
        content=_text(message.get("content") or ""),
        tool_calls=calls,
        usage=TokenUsage(
            input_tokens=_number(usage.get("prompt_tokens")),
            output_tokens=_number(usage.get("completion_tokens")),
            cache_read_tokens=_number(details.get("cached_tokens", 0)),
            cache_write_tokens=_number(details.get("cache_write_tokens", 0)),
        ),
        stop_reason=_text(choices[0].get("finish_reason") or "stop"),
    )


class OpenAIProvider:
    """Send explicit Chat Completions requests through an injectable HTTPX client."""

    def __init__(self, client: httpx.Client, *, api_key: str, url: str) -> None:
        """Keep credentials in headers, outside durable messages and traces."""
        self.client = client
        self.api_key = api_key
        self.url = url

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Adapt assistant tool calls and their correlated tool results."""
        payload = {
            "model": request.model,
            "messages": [_openai_message(message) for message in request.messages],
            "tools": [
                {"type": "function", "function": tool.model_dump(mode="json")}
                for tool in request.tools
            ],
            "max_completion_tokens": request.max_output_tokens,
        }
        response = self.client.post(
            self.url, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}
        )
        response.raise_for_status()
        return _openai_result(JsonDocument.model_validate(response.json()))


def _anthropic_message(message: ChatMessage) -> dict[str, JsonValue]:
    blocks: list[JsonValue] = []
    if message.role == "tool":
        blocks.append(
            {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content}
        )
    else:
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        blocks.extend(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.arguments.root,
            }
            for call in message.tool_calls
        )
    return {"role": "user" if message.role == "tool" else message.role, "content": blocks}


def _anthropic_result(data: JsonDocument) -> ModelResponse:
    blocks = _items(data.root.get("content", []))
    calls = [
        ToolCall(
            id=_text(block.get("id")),
            name=_text(block.get("name")),
            arguments=JsonDocument(_object(block.get("input"))),
        )
        for block in blocks
        if block.get("type") == "tool_use"
    ]
    usage = _object(data.root.get("usage"))
    read = _number(usage.get("cache_read_input_tokens") or 0)
    write = _number(usage.get("cache_creation_input_tokens") or 0)
    return ModelResponse(
        content="".join(
            _text(block.get("text")) for block in blocks if block.get("type") == "text"
        ),
        tool_calls=calls,
        usage=TokenUsage(
            input_tokens=_number(usage.get("input_tokens")) + read + write,
            output_tokens=_number(usage.get("output_tokens")),
            cache_read_tokens=read,
            cache_write_tokens=write,
        ),
        stop_reason=_text(data.root.get("stop_reason") or "end_turn"),
    )


class AnthropicProvider:
    """Send Messages requests, preserving tool_use and tool_result blocks."""

    def __init__(self, client: httpx.Client, *, api_key: str, url: str) -> None:
        """Inject transport and endpoint without importing a vendor SDK."""
        self.client = client
        self.api_key = api_key
        self.url = url

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Separate stable system text from the full alternating message history."""
        payload = {
            "model": request.model,
            "system": "\n\n".join(m.content for m in request.messages if m.role == "system"),
            "messages": [
                _anthropic_message(message)
                for message in request.messages
                if message.role != "system"
            ],
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters.root,
                }
                for tool in request.tools
            ],
            "max_tokens": request.max_output_tokens,
        }
        response = self.client.post(
            self.url,
            json=payload,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        response.raise_for_status()
        return _anthropic_result(JsonDocument.model_validate(response.json()))


class FakeProvider:
    """Replay an explicit script while retaining every request for assertions."""

    def __init__(self, script: list[ModelResponse]) -> None:
        """Copy the scripted response queue so fixtures cannot mutate it accidentally."""
        self.script = list(script)
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return the next script entry, deriving fixture usage when omitted."""
        self.requests.append(request)
        result = self.script.pop(0) if self.script else ModelResponse(content="Complete.")
        if result.usage.input_tokens:
            return result
        usage = TokenUsage(
            input_tokens=sum(segment.tokens for segment in request.segments),
            output_tokens=max(1, len(json.dumps(result.model_dump(mode="json"))) // 4),
        )
        return result.model_copy(update={"usage": usage})
