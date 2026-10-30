# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Send one prepared view to an OpenAI-compatible endpoint without retries or body leakage.

Failures become short codes (timeout, rate_limited, network_error, provider_error,
invalid_response). Provider bodies, headers and credentials never enter results or logs.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import NamedTuple

import httpx
from pydantic import JsonValue, ValidationError

from datakeel.core.prelabel_models import CloudModelConfig
from datakeel.core.transcription_wire import TranscriptionResponse
from datakeel.prelabel.images import SentImage

_HTTP_TOO_MANY_REQUESTS = 429
_TRANSPORT: ContextVar[httpx.BaseTransport | None] = ContextVar("prelabel_transport", default=None)


class ProviderReply(NamedTuple):
    """Reply text and measured usage, or a failure code with zero usage."""

    text: str
    input_tokens: int
    output_tokens: int
    elapsed_seconds: float
    failure: str | None = None
    usage_reported: bool = True


@contextmanager
def use_transport(transport: httpx.BaseTransport) -> Generator[None]:
    """Route prelabel requests through an injected transport, for recorded tests."""
    token = _TRANSPORT.set(transport)
    try:
        yield
    finally:
        _TRANSPORT.reset(token)


@contextmanager
def open_client() -> Generator[httpx.Client]:
    """Open a proxy-free, redirect-free client, honouring an injected transport."""
    transport = _TRANSPORT.get()
    with httpx.Client(transport=transport, trust_env=False, follow_redirects=False) as client:
        yield client


def request_body(config: CloudModelConfig, view: SentImage, prompt: str) -> dict[str, JsonValue]:
    """Build the chat-completions body with the image first and the instruction second."""
    return {
        **config.request_parameters,
        "model": config.model,
        "temperature": 0,
        "max_tokens": config.max_output_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": view.data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def _failure(code: str, started: float) -> ProviderReply:
    return ProviderReply("", 0, 0, perf_counter() - started, code)


def request_view(  # noqa: PLR0911  # One return per documented failure class keeps codes exact.
    config: CloudModelConfig,
    view: SentImage,
    prompt: str,
    client: httpx.Client,
    api_key: str,
) -> ProviderReply:
    """Post one view and map every failure class to a stable code."""
    started = perf_counter()
    try:
        response = client.post(
            config.base_url + "/chat/completions",
            json=request_body(config, view, prompt),
            headers={"accept": "application/json", "authorization": f"Bearer {api_key}"},
            timeout=config.timeout_seconds,
        )
    except httpx.TimeoutException:
        return _failure("timeout", started)
    except httpx.RequestError:
        return _failure("network_error", started)
    if response.status_code == _HTTP_TOO_MANY_REQUESTS:
        return _failure("rate_limited", started)
    if response.is_error:
        return _failure(f"provider_error_{response.status_code}", started)
    try:
        parsed = TranscriptionResponse.model_validate_json(response.content)
    except ValidationError:
        return _failure("invalid_response", started)
    if not parsed.choices:
        return _failure("invalid_response", started)
    usage = parsed.usage
    return ProviderReply(
        text=parsed.choices[0].message.content,
        input_tokens=usage.prompt_tokens or 0,
        output_tokens=usage.completion_tokens or 0,
        elapsed_seconds=perf_counter() - started,
        usage_reported=usage.prompt_tokens is not None and usage.completion_tokens is not None,
    )
