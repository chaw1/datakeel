# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The injected HTTP bridge preserves streaming instead of reading the whole response first."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.core.agent_models import ConversationCreate, ModelRequest
from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.settings import Settings
from datakeel.runtime.chat_provider import model_provider

if TYPE_CHECKING:
    from collections.abc import Iterator


class IncrementalBody(httpx.SyncByteStream):
    """Refuse the next transport frame until the previous text reaches the callback."""

    def __init__(self, deltas: list[str]) -> None:
        """Share the consumer's observations to make eager transport buffering observable."""
        self.deltas = deltas
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        """Pause at each yield so delivery must happen before requesting the next bytes."""
        yield self.frame("First ")
        assert self.deltas == ["First "], "HTTP bridge consumed ahead of the live callback"
        yield self.frame("second.")
        assert self.deltas == ["First ", "second."]
        usage = {"prompt_tokens": 13, "completion_tokens": 4, "total_tokens": 17}
        yield ("data: " + json.dumps({"choices": [], "usage": usage}) + "\n\n").encode()
        yield b"data: [DONE]\n\n"

    @staticmethod
    def frame(content: str) -> bytes:
        """Encode one valid completion frame without ending the surrounding stream."""
        return (
            "data: "
            + json.dumps(
                {
                    "id": "stream-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
            )
            + "\n\n"
        ).encode()

    def close(self) -> None:
        """Expose resource ownership when the SDK finishes consuming a stream."""
        self.closed = True


def test_injected_transport_delivers_each_delta_before_reading_the_remaining_http_body() -> None:
    """Exercise actual SDK SSE parsing and prove the HTTP bridge cannot buffer the body."""
    deltas: list[str] = []
    body = IncrementalBody(deltas)

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)

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
        response = provider.complete(
            ModelRequest(model="fixture-model", messages=[], tools=[], segments=[]),
            on_text_delta=deltas.append,
        )
    assert response.content == "First second."
    assert response.usage == TokenUsage(input_tokens=13, output_tokens=4)
    assert body.closed


class TimeoutBody(IncrementalBody):
    """Fail after the first visible token to exercise transport failures during iteration."""

    def __iter__(self) -> Iterator[bytes]:
        """Produce one chunk before a local simulated network read timeout."""
        yield self.frame("First ")
        message = "Fixture streaming timeout"
        raise httpx.ReadTimeout(message)


def test_midstream_transport_timeout_stays_a_retryable_provider_error() -> None:
    """A timeout after headers retains normal fallback semantics and closes the response."""
    deltas: list[str] = []
    body = TimeoutBody(deltas)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=body
                )
            ),
            trust_env=False,
        ) as client,
        model_provider(
            ConversationCreate(provider="openai"),
            Settings.model_validate({"openai_api_key": "fixture-key"}),
            client,
        ) as provider,
        pytest.raises(ProviderError, match="Model provider") as error,
    ):
        provider.complete(
            ModelRequest(model="fixture-model", messages=[], tools=[], segments=[]),
            on_text_delta=deltas.append,
        )
    assert error.value.retryable
    assert error.value.reason == "timeout"
    assert deltas == ["First "]
    assert body.closed
