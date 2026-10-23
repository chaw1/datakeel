# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider configuration is opt-in and HTTP lifetimes remain bounded."""

from __future__ import annotations

from typing import Literal

import httpx
import pytest

from datakeel.agent.factory import provider_session
from datakeel.agent.providers import AnthropicProvider, FakeProvider, OpenAIProvider
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ValidationError


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_provider_factory_when_key_missing_rejects_network_setup(
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["openai", "anthropic"],
) -> None:
    """Fail locally without asking a network service to discover missing credentials."""
    monkeypatch.delenv(f"DATAKEEL_{kind.upper()}_API_KEY", raising=False)
    with (
        pytest.raises(ValidationError, match="No API key"),
        provider_session(ConversationCreate(provider=kind)),
    ):
        pytest.fail("Missing credentials unexpectedly constructed a provider")


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_provider_factory_when_configured_closes_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["openai", "anthropic"],
) -> None:
    """Exercise real adapter selection with an in-process transport and synthetic key."""
    monkeypatch.setenv(f"DATAKEEL_{kind.upper()}_API_KEY", "synthetic-fixture")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    def factory(*, timeout: float, trust_env: bool) -> httpx.Client:
        assert timeout == 30
        assert trust_env is False
        return client

    monkeypatch.setattr("datakeel.agent.factory.httpx.Client", factory)
    with provider_session(ConversationCreate(provider=kind)) as provider:
        assert isinstance(provider, OpenAIProvider if kind == "openai" else AnthropicProvider)
    assert client.is_closed


def test_provider_factory_when_fixture_supplied_uses_it_without_configuration() -> None:
    """Allow fake integrations to replace any configured vendor protocol."""
    fixture = FakeProvider([])
    with provider_session(ConversationCreate(provider="openai"), fixture) as provider:
        assert provider is fixture
