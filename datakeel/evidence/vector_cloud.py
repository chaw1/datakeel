# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retry-free OpenAI-compatible HTTP embedding transport with predispatch fencing."""

from __future__ import annotations

import contextvars
import ipaddress
import re
import socket
import threading
from contextlib import contextmanager
from http import HTTPStatus
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import ConfigDict, Field, ValidationError

from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings
from datakeel.core.vector_models import EmbedParams, FrozenVectorNode, VectorError

if TYPE_CHECKING:
    from collections.abc import Generator

    from datakeel.evidence.vector_payload import PreparedWire
    from datakeel.evidence.vector_transport import VectorDispatchGate

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_.:-]+$")
_TIMEOUT_SECONDS = 30.0
_TRANSPORT_LOCK = threading.Lock()
_SHARED_TRANSPORTS: list[httpx.BaseTransport] = []
_TRANSPORT_OVERRIDE: contextvars.ContextVar[httpx.BaseTransport | None] = contextvars.ContextVar(
    "vector_cloud_transport", default=None
)


def _current_transport() -> httpx.BaseTransport | None:
    override = _TRANSPORT_OVERRIDE.get()
    if override is not None:
        return override
    with _TRANSPORT_LOCK:
        return _SHARED_TRANSPORTS[-1] if _SHARED_TRANSPORTS else None


@contextmanager
def use_cloud_vector_transport(transport: httpx.BaseTransport) -> Generator[None]:
    """Bind an explicit HTTP transport across worker pool threads for offline tests."""
    reset = _TRANSPORT_OVERRIDE.set(transport)
    with _TRANSPORT_LOCK:
        _SHARED_TRANSPORTS.append(transport)
    try:
        yield
    finally:
        with _TRANSPORT_LOCK:
            _SHARED_TRANSPORTS.remove(transport)
        _TRANSPORT_OVERRIDE.reset(reset)


class CloudUsage(BoundaryModel):
    """Validate billed token counts returned by an OpenAI-compatible embedding endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    prompt_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int = Field(ge=0, strict=True)


class CloudEmbeddingItem(BoundaryModel):
    """Map one embedding vector to the single-item request index."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    object: Literal["embedding"] = "embedding"
    index: int = Field(ge=0, strict=True)
    embedding: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]


class CloudEmbeddingResponse(BoundaryModel):
    """Validate OpenAI and DashScope compatible-mode /v1/embeddings JSON responses."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str | None = Field(default=None, min_length=1, max_length=200)
    object: Literal["list"] = "list"
    model: str = Field(min_length=1, max_length=200)
    data: tuple[CloudEmbeddingItem, ...]
    usage: CloudUsage


def _resolve_api_key(params: EmbedParams) -> str:
    if params.credential_env is None:
        return ""
    secret = get_settings().extraction_key(params.credential_env)
    value = secret.get_secret_value().strip() if secret is not None else ""
    if not value:
        msg = "vector_missing_credentials"
        raise VectorError(msg)
    return value


def _verify_destination(endpoint: str, *, custom_transport: bool) -> None:
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or "").lower()
    if host in _LOOPBACK_HOSTS or custom_transport:
        return
    port = parsed.port or 443
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        msg = "vector_provider_unreachable"
        raise VectorError(msg) from None
    if not infos:
        msg = "vector_provider_unreachable"
        raise VectorError(msg)
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            msg = "vector_unsafe_destination"
            raise VectorError(msg)


def _response_id(parsed: CloudEmbeddingResponse, response: httpx.Response, attempt_id: str) -> str:
    candidate = parsed.id or response.headers.get("x-request-id") or f"cloud_{attempt_id}"
    return candidate[:200] if _SAFE_ID.fullmatch(candidate) else f"cloud_{attempt_id}"


class CloudVectorTransport:
    """Execute one authorized non-retrying HTTPS/loopback /v1/embeddings call."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        """Use an injected test transport or a clean trust_env=False network client."""
        self._transport = transport or _current_transport()

    def send(
        self,
        gate: VectorDispatchGate,
        node: FrozenVectorNode,
        wire: PreparedWire,
        attempt_id: str,
    ) -> tuple[tuple[float, ...], int, str]:
        """Verify credentials and destination before SENDING, then validate response strictly."""
        gate.verify()
        api_key = _resolve_api_key(node.params)
        _verify_destination(node.params.endpoint, custom_transport=self._transport is not None)
        gate.commit()
        headers = {"content-type": "application/json", "accept": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        try:
            with httpx.Client(
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            ) as client:
                reply = client.post(node.params.endpoint, content=wire.body, headers=headers)
        except httpx.TimeoutException:
            msg = "vector_provider_timeout"
            raise VectorError(msg) from None
        except httpx.RequestError:
            msg = "vector_provider_unreachable"
            raise VectorError(msg) from None
        return _parse_reply(reply, node, attempt_id)


def _parse_reply(
    reply: httpx.Response, node: FrozenVectorNode, attempt_id: str
) -> tuple[tuple[float, ...], int, str]:
    status = reply.status_code
    if HTTPStatus.MULTIPLE_CHOICES <= status < HTTPStatus.BAD_REQUEST:
        msg = "vector_redirect_refused"
        raise VectorError(msg)
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        msg = "vector_authentication_failed"
        raise VectorError(msg)
    if status in {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}:
        msg = "vector_temporary_input_failure"
        raise VectorError(msg)
    if status != HTTPStatus.OK:
        msg = "vector_protocol_failure"
        raise VectorError(msg)
    try:
        parsed = CloudEmbeddingResponse.model_validate_json(reply.content)
    except ValidationError:
        msg = "vector_invalid_response"
        raise VectorError(msg) from None
    if (
        parsed.model != node.params.effective_model()
        or len(parsed.data) != 1
        or parsed.data[0].index != 0
        or len(parsed.data[0].embedding) != node.params.dimensions
    ):
        msg = "vector_response_mapping_invalid"
        raise VectorError(msg)
    return (
        parsed.data[0].embedding,
        parsed.usage.total_tokens,
        _response_id(parsed, reply, attempt_id),
    )
