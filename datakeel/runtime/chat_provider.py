# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Construct retry-free vendor chat models over the injected HTTP transport."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from functools import cached_property

import httpx
import httpx2
from anthropic import Anthropic
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import Field, JsonValue

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.runtime.chat import ChatProvider


class _Transport(httpx2.BaseTransport):
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        """Bridge HTTP library generations without interpreting any model protocol."""
        try:
            response = self.client.request(
                request.method,
                str(request.url),
                headers=request.headers.multi_items(),
                content=request.read(),
            )
        except httpx.TimeoutException as error:
            message = "Model transport timeout"
            raise httpx2.ReadTimeout(message, request=request) from error
        return httpx2.Response(
            response.status_code,
            headers=[
                (name, value)
                for name, value in response.headers.multi_items()
                if name.lower() not in {"content-encoding", "content-length"}
            ],
            content=response.content,
        )


class _AnthropicModel(ChatAnthropic):
    transport: httpx2.Client = Field(exclude=True)

    @cached_property
    def _client(self) -> Anthropic:
        return Anthropic(**self._client_params, http_client=self.transport)


def _base_url(config: ConversationCreate, settings: Settings) -> str:
    modern = (
        settings.openai_base_url if config.provider == "openai" else settings.anthropic_base_url
    )
    if modern:
        return modern.rstrip("/")
    legacy = settings.openai_url if config.provider == "openai" else settings.anthropic_url
    suffix = "/chat/completions" if config.provider == "openai" else "/v1/messages"
    if not legacy.endswith(suffix):
        msg = "Deprecated provider URL must end with the standard endpoint; use BASE_URL"
        raise ValidationError(msg)
    return legacy.removesuffix(suffix)


def _openai_parameters(parameters: Mapping[str, JsonValue]) -> dict[str, object]:
    # reasoning_effort is a native field; vendor switches such as enable_thinking go in the body.
    options: dict[str, object] = {}
    extra = {key: value for key, value in parameters.items() if key != "reasoning_effort"}
    if "reasoning_effort" in parameters:
        options["reasoning_effort"] = parameters["reasoning_effort"]
    if extra:
        options["extra_body"] = extra
    return options


@contextmanager
def model_provider(
    config: ConversationCreate,
    settings: Settings,
    client: httpx.Client,
    request_parameters: Mapping[str, JsonValue] | None = None,
) -> Generator[ChatProvider]:
    """Use the owned HTTP client for all synchronous SDK requests and disable retries."""
    key = settings.openai_api_key if config.provider == "openai" else settings.anthropic_api_key
    if key is None:
        msg = f"No API key configured for {config.provider}"
        raise ValidationError(msg)
    parameters = dict(request_parameters or {})
    if parameters and config.provider != "openai":
        msg = "request_parameters require the openai provider"
        raise ValidationError(msg)
    with httpx2.Client(transport=_Transport(client), trust_env=False) as transport:
        options = {
            "model": config.model,
            "api_key": key,
            "base_url": _base_url(config, settings),
            "max_retries": 0,
            "timeout": settings.provider_timeout,
            "cache": False,
        }
        model = (
            ChatOpenAI.model_validate(
                {
                    **options,
                    **_openai_parameters(parameters),
                    "http_client": transport,
                    "http_socket_options": (),
                    "async_client": object(),
                }
            )
            if config.provider == "openai"
            else _AnthropicModel.model_validate({**options, "transport": transport})
        )
        yield ChatProvider(model)
