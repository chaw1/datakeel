# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synthetic same-provider prices and transport responses for offline fallback fixtures."""

import json
from pathlib import Path
from typing import Literal

import httpx
import pytest
import yaml
from pydantic import JsonValue

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.settings import Settings
from datakeel.routing.config import load_config, load_prices

ProtocolKind = Literal["openai", "anthropic"]


def configure_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: ProtocolKind
) -> tuple[ConversationCreate, Settings, str]:
    """Install a temporary, priced fallback using only generated fixture model names."""
    table = load_prices()
    template = next(price for price in table.models if price.provider == kind)
    backup = f"{kind}-fixture-backup"
    table = table.model_copy(
        update={"models": [*table.models, template.model_copy(update={"model": backup})]}
    )
    monkeypatch.setattr("datakeel.routing.config.load_prices", lambda: table)
    config = load_config()
    providers = dict(config.providers)
    providers[kind] = providers[kind].model_copy(update={"fallbacks": {template.model: backup}})
    path = tmp_path / "routing.yaml"
    path.write_text(yaml.safe_dump(config.model_copy(update={"providers": providers}).model_dump()))
    monkeypatch.setenv("DATAKEEL_MODEL_ROUTING_FILE", str(path))
    return (
        ConversationCreate(provider=kind, model="auto"),
        Settings.model_validate(
            {f"{kind}_api_key": "fixture-key", f"{kind}_base_url": "https://fixture.invalid"}
        ),
        backup,
    )


def successful_payload(
    kind: ProtocolKind, model: str, content: str = "Recovered response."
) -> dict[str, JsonValue]:
    """Return minimal genuine-protocol completion and usage fields."""
    if kind == "openai":
        return {
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        }
    return {
        "id": "msg-fixture",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": content}],
        "usage": {"input_tokens": 8, "output_tokens": 4},
        "stop_reason": "end_turn",
    }


def protocol_response(
    request: httpx.Request,
    kind: ProtocolKind,
    model: str,
    content: str = "Recovered response.",
) -> httpx.Response:
    """Return SSE chunks when stream=True is requested, or JSON completion otherwise."""
    payload = json.loads(request.content)
    if payload.get("stream") is not True:
        return httpx.Response(200, json=successful_payload(kind, model, content))
    body = _openai_sse(model, content) if kind == "openai" else _anthropic_sse(model, content)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)


def _openai_sse(model: str, content: str) -> bytes:
    chunk = {
        "id": "chatcmpl-fixture",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    usage = {
        "id": "chatcmpl-fixture",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": model,
        "choices": [],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    }
    return f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode()


def _anthropic_sse(model: str, content: str) -> bytes:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg-fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 8, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": content},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 4},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(item)}\n\n" for name, item in events).encode()


class FailingTransport:
    """Record wire model selection and fail exactly the first request."""

    def __init__(
        self, kind: ProtocolKind, failure: int | Literal["timeout"], *, repeat: bool = False
    ) -> None:
        """Keep all fixture state in memory; no sockets or credentials are used."""
        self.kind: ProtocolKind = kind
        self.failure: int | Literal["timeout"] = failure
        self.repeat = repeat
        self.models: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return an actual protocol response after the selected transient failure."""
        model = str(json.loads(request.content)["model"])
        self.models.append(model)
        if len(self.models) > 1 and not self.repeat:
            return protocol_response(request, self.kind, model)
        if self.failure == "timeout":
            message = "fixture timeout"
            raise httpx.ReadTimeout(message, request=request)
        return httpx.Response(
            self.failure, json={"error": {"message": "fixture failure", "type": "api_error"}}
        )
