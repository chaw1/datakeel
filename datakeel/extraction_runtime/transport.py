# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Own retry-free synchronous SDK transport without reading model credentials."""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from functools import cached_property
from typing import Literal, Protocol, cast

import httpx
import httpx2
import langsmith
from anthropic import Anthropic
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.kg_contracts import ExtractionProfile


class _TracingAPI(Protocol):
    def tracing_context(
        self, *, enabled: bool, parent: Literal[False]
    ) -> AbstractContextManager[None]: ...


@contextmanager
def tracing_disabled() -> Generator[None]:
    """Disable inherited global tracing and invocation-local parent tracing."""
    langsmith.configure(enabled=False)
    with cast("_TracingAPI", langsmith).tracing_context(enabled=False, parent=False):
        yield


class _Transport(httpx2.BaseTransport):
    def __init__(self, client: httpx.Client, provider: str, api_key: str) -> None:
        self.client = client
        self.headers = {"accept": "application/json", "content-type": "application/json"}
        if provider == "anthropic":
            self.headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        else:
            self.headers["authorization"] = f"Bearer {api_key}"

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        """Send every SDK request through the caller's explicitly owned client."""
        try:
            response = self.client.request(
                request.method,
                str(request.url),
                headers=self.headers,
                content=request.read(),
                extensions=request.extensions,
                follow_redirects=False,
            )
        except httpx.TimeoutException as error:
            message = "Extraction transport timeout"
            raise httpx2.ReadTimeout(message, request=request) from error
        except httpx.RequestError as error:
            message = "Extraction transport failed"
            raise httpx2.ConnectError(message, request=request) from error
        return httpx2.Response(
            response.status_code, headers=response.headers.multi_items(), content=response.content
        )


class _AnthropicModel(ChatAnthropic):
    transport: httpx2.Client = Field(exclude=True)

    @cached_property
    def _client(self) -> Anthropic:
        return Anthropic(**self._client_params, http_client=self.transport, webhook_key="")


def _base_url(profile: ExtractionProfile) -> str:
    if profile.base_url:
        return profile.base_url
    defaults = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com"}
    value = defaults.get(profile.provider)
    if value is None:
        message = "The selected extraction provider requires an explicit base_url"
        raise ValidationError(message)
    return value


def _openai_model(
    options: dict[str, object],
    profile: ExtractionProfile,
    api_key: str,
    transport: httpx2.Client,
    timeout: float,
) -> ChatOpenAI:
    root = OpenAI(
        api_key=api_key,
        base_url=_base_url(profile),
        http_client=transport,
        timeout=timeout,
        max_retries=0,
        admin_api_key="",
        organization="",
        project="",
        webhook_secret="",
    )
    return ChatOpenAI.model_validate(
        {
            **options,
            "http_client": transport,
            "http_socket_options": (),
            "async_client": object(),
            "root_client": root,
            "client": root.chat.completions,
            "openai_proxy": None,
        }
    )


@contextmanager
def chat_model(
    profile: ExtractionProfile, api_key: str, client: httpx.Client, timeout: float
) -> Generator[ChatOpenAI | ChatAnthropic]:
    """Configure supported providers with explicit credentials and zero SDK retries."""
    if profile.provider not in {"openai", "anthropic", "ollama"}:
        message = "LLM extraction requires an OpenAI-compatible or Anthropic provider"
        raise ValidationError(message)
    if not api_key:
        message = "LLM extraction requires an explicitly supplied API key"
        raise ValidationError(message)
    with httpx2.Client(
        transport=_Transport(client, profile.provider, api_key), trust_env=False
    ) as transport:
        options: dict[str, object] = {
            "model": profile.model,
            "api_key": api_key,
            "base_url": _base_url(profile),
            "max_retries": 0,
            "timeout": timeout,
            "cache": False,
            "temperature": profile.temperature,
            "max_tokens": profile.max_output_tokens,
        }
        model = (
            _openai_model(options, profile, api_key, transport, timeout)
            if profile.provider != "anthropic"
            else _AnthropicModel.model_validate(
                {**options, "transport": transport, "anthropic_proxy": None}
            )
        )
        yield model
