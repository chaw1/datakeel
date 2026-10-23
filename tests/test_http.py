# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP helpers isolate proxy settings and bound local verification requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from datakeel.http import Client, Response

if TYPE_CHECKING:
    import pytest


def test_client_when_ambient_proxy_configured_does_not_enable_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify client when ambient proxy configured does not enable proxy."""
    monkeypatch.setenv("HTTP_PROXY", "http://unrelated.invalid:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://unrelated.invalid:3128")
    with Client("http://127.0.0.1:8765", timeout=2.5) as client:
        assert client.trust_env is False
        assert client.timeout == httpx.Timeout(2.5)


def test_client_when_mocked_transport_used_resolves_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify client when mocked transport used resolves relative path."""
    requests = []

    def respond(request: httpx.Request) -> Response:
        """Provide the respond test fixture."""
        requests.append(request)
        return Response(200, json={"status": "ok"})

    with Client("http://127.0.0.1:8765") as client:
        monkeypatch.setattr(client, "_transport", httpx.MockTransport(respond))
        response = client.get("/api/health")
    assert response.json() == {"status": "ok"}
    assert str(requests[0].url) == "http://127.0.0.1:8765/api/health"
