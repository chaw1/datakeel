# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for report."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Never, TypedDict
from urllib.request import ProxyHandler, Request

import pytest

from datakeel.core.models import FileItem
from datakeel.quality import build_report, score_quality

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import JsonValue

    from datakeel.quality.models import QualityView


class EndpointState(TypedDict):
    """Keep the local HTTP stub's request and response observations typed."""

    payload: dict[str, JsonValue]
    status: int
    paths: list[str]
    requests: list[dict[str, JsonValue]]


type EndpointFixture = tuple[str, EndpointState]


@pytest.fixture
def quality() -> QualityView:
    """Provide the quality test fixture."""
    return score_quality(
        [FileItem(path="objects/a", filename="a.txt", size=10, modality="text", sha256="a" * 64)]
    )


@pytest.fixture
def endpoint() -> Iterator[EndpointFixture]:
    """Provide the endpoint test fixture."""
    state: EndpointState = {
        "payload": {"choices": [{"message": {"content": "Grounded report"}}]},
        "status": 200,
        "paths": [],
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            """Provide the do POST test fixture."""
            state["paths"].append(self.path)
            state["requests"].append(
                json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            )
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            if state["status"] in (301, 302, 307, 308):
                self.send_header("Location", "/followed")
            self.end_headers()
            self.wfile.write(json.dumps(state["payload"]).encode())

        def do_GET(self) -> None:
            """Provide the do GET test fixture."""
            state["paths"].append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(state["payload"]).encode())

        def log_message(self, *args: object) -> None:
            """Provide the log message test fixture."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/chat", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_six_baseline_chapters_and_verification(quality: QualityView) -> None:
    """Verify six baseline chapters and verification."""
    report = build_report({"name": "Example"}, quality)
    assert [chapter["title"] for chapter in report["chapters"]] == [
        "概览",
        "质量结论",
        "适用场景",
        "潜在问题",
        "治理建议",
        "README 草案",
    ]
    assert report["source"] == "baseline"
    assert report["fallback"] is False
    assert report["body"].endswith(report["baseline_verification"])
    assert "100.0/100" in report["body"]


def test_invalid_llm_address_falls_back(quality: QualityView) -> None:
    """Verify invalid llm address falls back."""
    report = build_report({"name": "Example"}, quality, "not-a-valid-url")
    assert report["fallback"] is True
    assert report["source"] == "baseline"
    assert len(report["chapters"]) == 6
    assert report["body"].startswith("## 概览")


def test_llm_success_keeps_baseline_and_appends_verification(
    endpoint: EndpointFixture, quality: QualityView
) -> None:
    """Verify llm success keeps baseline and appends verification."""
    url, state = endpoint
    report = build_report(
        {"name": "Example", "metadata": {"private_value": "local-only"}}, quality, url
    )
    assert report["source"] == "llm"
    assert report["body"].startswith("Grounded report")
    assert report["body"].endswith(report["baseline_verification"])
    assert "## 概览" in report["baseline"]
    assert state["requests"][0]["messages"][1]["content"] == report["baseline"]
    assert "local-only" not in json.dumps(state["requests"])


@pytest.mark.parametrize(
    "payload", [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}]
)
def test_malformed_llm_payload_falls_back(
    endpoint: EndpointFixture, quality: QualityView, payload: dict[str, JsonValue]
) -> None:
    """Verify malformed llm payload falls back."""
    url, state = endpoint
    state["payload"] = payload
    assert build_report({"name": "Example"}, quality, url)["fallback"] is True


def test_llm_timeout_falls_back_and_disables_proxy_handlers(
    monkeypatch: pytest.MonkeyPatch, quality: QualityView
) -> None:
    """Verify llm timeout falls back and disables proxy handlers."""

    class Opener:
        def open(self, request: Request, timeout: float) -> Never:
            """Provide the open test fixture."""
            assert request.get_method() == "POST"
            assert timeout == 2.0
            msg = "timed out"
            raise TimeoutError(msg)

    def create_opener(*handlers: object) -> Opener:
        """Provide the create opener test fixture."""
        assert any(
            isinstance(handler, ProxyHandler) and handler.proxies == {} for handler in handlers
        )
        return Opener()

    monkeypatch.setattr("datakeel.quality.report.build_opener", create_opener)
    assert (
        build_report({"name": "Example"}, quality, "https://example.test/chat")["fallback_reason"]
        == "TimeoutError"
    )


@pytest.mark.parametrize("status", [302, 307, 500])
def test_llm_http_failures_and_redirects_fall_back(
    endpoint: EndpointFixture, quality: QualityView, status: int
) -> None:
    """Verify llm http failures and redirects fall back."""
    url, state = endpoint
    state["status"] = status
    report = build_report({"name": "Example"}, quality, url)
    assert report["fallback"] is True
    assert state["paths"] == ["/chat"]


def test_llm_ignores_environment_proxy(
    endpoint: EndpointFixture, monkeypatch: pytest.MonkeyPatch, quality: QualityView
) -> None:
    """Verify llm ignores environment proxy."""
    url, _state = endpoint
    monkeypatch.setenv("http_proxy", "socks5://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "socks5://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")
    assert build_report({"name": "Example"}, quality, url)["source"] == "llm"
