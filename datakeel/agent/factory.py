# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve configured providers while keeping the default demo fully offline."""

from collections.abc import Generator
from contextlib import contextmanager

import httpx

from datakeel.agent.demo import DemoProvider
from datakeel.core.agent_models import ConversationCreate, Provider
from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.runtime.chat_provider import model_provider


@contextmanager
def provider_session(
    config: ConversationCreate, supplied: Provider | None = None
) -> Generator[Provider]:
    """Use an injected fixture or close the configured provider's HTTP client reliably."""
    if supplied is not None:
        yield supplied
        return
    if config.provider == "fake":
        yield DemoProvider()
        return
    settings = get_settings()
    secret = settings.openai_api_key if config.provider == "openai" else settings.anthropic_api_key
    if secret is None:
        msg = f"No API key configured for {config.provider}"
        raise ValidationError(msg)
    with (
        httpx.Client(timeout=settings.provider_timeout, trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        yield provider
