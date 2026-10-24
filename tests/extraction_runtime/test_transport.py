# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check HTTP error classification, explicit credentials and hostile tracing settings."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

import httpx
import pytest
from langsmith import configure
from langsmith.utils import tracing_is_enabled

from datakeel.core.errors import ProviderError, ValidationError
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.extraction_runtime.adapter import llm_extractor
from datakeel.extraction_runtime.transport import chat_model, tracing_disabled

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import TextBlock


def _profile(provider: str) -> ExtractionProfile:
    return ExtractionProfile(
        id="fixture",
        extractor="fake" if provider == "fake" else "llm",
        provider=provider,
        model="fixture-model",
        base_url="https://fixture.invalid/v1",
        output_method="json_mode",
    )


@pytest.mark.parametrize("provider", ["openai", "anthropic", "ollama"])
@pytest.mark.parametrize("failure", ["timeout", "connection", "status"])
def test_transport_when_request_fails_classifies_once_without_sdk_retry(
    schema: KGSchema, block: TextBlock, provider: str, failure: str
) -> None:
    """Retain failure categories and ensure each extraction attempt uses one HTTP request."""
    attempts: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if failure == "timeout":
            message = "Synthetic timeout"
            raise httpx.ReadTimeout(message, request=request)
        if failure == "connection":
            message = "Synthetic connection failure"
            raise httpx.ConnectError(message, request=request)
        return httpx.Response(
            429, json={"error": {"type": "rate_limit_error", "message": "Synthetic limit"}}
        )

    with (
        httpx.Client(transport=httpx.MockTransport(fail), trust_env=False) as client,
        llm_extractor(_profile(provider), "fixture-key", client) as extractor,
        pytest.raises(ProviderError) as captured,
    ):
        extractor.extract(block, schema)
    expected = {"timeout": "timeout", "connection": "provider_error", "status": "http_429"}
    assert captured.value.reason == expected[failure]
    assert len(attempts) == 1


@pytest.mark.parametrize(("provider", "key"), [("fake", "fixture-key"), ("openai", "")])
def test_transport_when_configuration_invalid_rejects_before_any_request(
    provider: str, key: str
) -> None:
    """Never fall back to a process credential or vendor when explicit configuration is absent."""
    attempts: list[httpx.Request] = []
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (attempts.append(request), httpx.Response(500))[1]
            )
        ) as client,
        pytest.raises(ValidationError),
        chat_model(_profile(provider), key, client, 3),
    ):
        pytest.fail("Invalid configuration must fail before yielding a model")
    assert attempts == []


def test_transport_when_tracing_enabled_only_injected_http_peer_receives_source(
    schema: KGSchema, block: TextBlock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disable ambient tracing and reject every DNS or socket attempt during model invocation."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-tracing-fixture")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://trace-fixture.invalid")
    attempts: list[httpx.Request] = []

    def forbid(*args: object, **kwargs: object) -> None:
        pytest.fail("Unexpected network access outside the injected HTTP transport")

    def respond(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        assert tracing_is_enabled() is False
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"entities":[],"relations":[]}'}}
                ]
            },
        )

    monkeypatch.setattr(socket.socket, "connect", forbid)
    monkeypatch.setattr(socket.socket, "connect_ex", forbid)
    monkeypatch.setattr(socket, "getaddrinfo", forbid)
    configure(enabled=True)
    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        llm_extractor(_profile("openai"), "fixture-key", client) as extractor,
    ):
        extractor.extract(block, schema)
        assert not client.is_closed
    assert tracing_is_enabled() is False
    assert len(attempts) == 1


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai", "https://api.openai.com/v1/chat/completions"),
        ("anthropic", "https://api.anthropic.com/v1/messages"),
    ],
)
def test_transport_when_base_url_omitted_ignores_ambient_provider_destinations(
    monkeypatch: pytest.MonkeyPatch, provider: str, expected: str
) -> None:
    """Keep the destination identical to the host approved in the frozen extraction plan."""
    for name in ("OPENAI_API_BASE", "OPENAI_BASE_URL", "ANTHROPIC_API_URL", "ANTHROPIC_BASE_URL"):
        monkeypatch.setenv(name, "https://unapproved-fixture.invalid/v1")
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if provider == "openai":
            payload = {
                "choices": [
                    {"message": {"role": "assistant", "content": '{"entities":[],"relations":[]}'}}
                ]
            }
        else:
            payload = {
                "id": "msg-fixture",
                "type": "message",
                "role": "assistant",
                "model": "fixture-model",
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return httpx.Response(200, json=payload)

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        chat_model(
            _profile(provider).model_copy(update={"base_url": None}), "fixture-key", client, 3
        ) as model,
        tracing_disabled(),
    ):
        model.invoke("Synthetic prompt")
    assert requested == [expected]


def test_transport_when_ollama_endpoint_missing_rejects_without_vendor_default() -> None:
    """A missing local-provider URL cannot silently redirect extraction to a cloud provider."""
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client,
        pytest.raises(ValidationError, match="explicit base_url"),
        chat_model(
            _profile("ollama").model_copy(update={"base_url": None}), "fixture-key", client, 3
        ),
    ):
        pytest.fail("A missing Ollama URL must fail before yielding a model")


def _empty_reply(provider: str) -> dict[str, JsonValue]:
    content = '{"entities":[],"relations":[]}'
    if provider == "openai":
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return {
        "id": "msg-fixture",
        "type": "message",
        "role": "assistant",
        "model": "fixture-model",
        "content": [{"type": "text", "text": content}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_transport_when_vendor_environment_hostile_keeps_only_explicit_protocol_headers(
    monkeypatch: pytest.MonkeyPatch, schema: KGSchema, block: TextBlock, provider: str
) -> None:
    """Ambient authentication, routing, organization and arbitrary headers never reach the peer."""
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_ADMIN_KEY",
        "OPENAI_WEBHOOK_SECRET",
        "OPENAI_ORG_ID",
        "OPENAI_ORGANIZATION",
        "OPENAI_PROJECT_ID",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_WEBHOOK_SIGNING_KEY",
    ):
        monkeypatch.setenv(name, "synthetic-ambient-secret")
    for name in ("OPENAI_PROXY", "ANTHROPIC_PROXY"):
        monkeypatch.setenv(name, "http://unapproved-fixture.invalid:9999")
    headers = (
        "Authorization: Bearer synthetic-ambient-secret\nX-Api-Key: synthetic-ambient-secret\n"
        "Host: unapproved-fixture.invalid\nAnthropic-Version: 2000-01-01\n"
        "Content-Type: text/plain\nX-Ambient-Secret: synthetic-ambient-secret"
    )
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", headers)
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", headers)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "synthetic-ambient-secret" not in str(request.headers)
        assert request.headers["host"] == "fixture.invalid"
        assert request.headers["content-type"] == "application/json"
        assert "x-ambient-secret" not in request.headers
        if provider == "openai":
            assert request.headers["authorization"] == "Bearer fixture-key"
            assert "x-api-key" not in request.headers
        else:
            assert request.headers["x-api-key"] == "fixture-key"
            assert request.headers["anthropic-version"] == "2023-06-01"
            assert "authorization" not in request.headers
        return httpx.Response(200, json=_empty_reply(provider))

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        llm_extractor(_profile(provider), "fixture-key", client) as extractor,
    ):
        extractor.extract(block, schema)
    assert len(requests) == 1
