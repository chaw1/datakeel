# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real HTTP OTLP response, retry, and partial-success checks."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from datakeel.core.errors import ExecutionError
from datakeel.core.harness_models import BudgetRequest, TokenSegment, TokenUsage, TraceInput
from datakeel.harness.otel import export_traces
from datakeel.harness.service import reserve, settle

if TYPE_CHECKING:
    from collections.abc import Iterator

    from datakeel.storage.database import Database


@dataclass
class Response:
    """One scripted local HTTP response."""

    status: int = 200
    body: bytes = b""
    retry_after: str | None = None


class Capture:
    """Own request evidence without writing response bodies to logs."""

    def __init__(self, responses: list[Response]) -> None:
        """Script a finite sequence, repeating the last response if necessary."""
        self.responses = responses
        self.paths: list[str] = []
        self.content_types: list[str | None] = []
        self.authorizations: list[str | None] = []


@pytest.fixture
def server() -> Iterator[type[Capture]]:
    """Start real loopback HTTP servers with unique synthetic response scripts."""
    running: list[HTTPServer] = []

    class Factory(type):
        """Class-level capture factory matching the test fixture style."""

    def start(responses: list[Response]) -> tuple[Capture, str]:
        capture = Capture(responses)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # stdlib handler API
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                capture.paths.append(self.path)
                capture.content_types.append(self.headers.get("Content-Type"))
                capture.authorizations.append(self.headers.get("Authorization"))
                index = min(len(capture.paths) - 1, len(capture.responses) - 1)
                response = capture.responses[index]
                self.send_response(response.status)
                if response.retry_after is not None:
                    self.send_header("Retry-After", response.retry_after)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                self.wfile.write(response.body)

            def log_message(self, _format: str, *args: object) -> None:
                """Keep synthetic requests out of test output."""

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        running.append(httpd)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return capture, f"http://127.0.0.1:{httpd.server_port}/v1/traces"

    Factory.start = staticmethod(start)  # type: ignore[attr-defined]
    yield Factory
    for httpd in running:
        httpd.shutdown()
        httpd.server_close()


def seed_trace(db: Database) -> None:
    """Persist one measured conversation call through the normal metering path."""
    reservation = reserve(
        db,
        BudgetRequest(
            conversation_id="fixture", model="fake-script", input_tokens=100, max_output_tokens=20
        ),
    )
    settle(
        db,
        reservation.id,
        TraceInput(
            conversation_id="fixture",
            turn=1,
            model="fake-script",
            provider="fake",
            segments=[TokenSegment(name="user", tokens=100)],
            usage=TokenUsage(input_tokens=100, output_tokens=10),
            latency_ms=1,
            stop_reason="stop",
            tool_calls=0,
        ),
    )


def export_failed(db: Database) -> bool:
    """Return only an expected export failure, leaving unexpected exceptions unhandled."""
    try:
        export_traces(db)
    except ExecutionError:
        return True
    return False


def configure(monkeypatch: pytest.MonkeyPatch, endpoint: str) -> None:
    """Point the real fixed exporter at a local capture."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "Authorization=Basic sentinel-header")


def test_http_when_200_accepts_protobuf_and_expected_header(
    db: Database,
    server: type[Capture],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A real HTTP 200 empty OTLP response accepts all spans without leaking headers."""
    capture, endpoint = server.start([Response()])
    configure(monkeypatch, endpoint)
    seed_trace(db)
    assert export_traces(db) == 2
    assert capture.paths == ["/v1/traces"]
    assert capture.content_types == ["application/x-protobuf"]
    assert capture.authorizations == ["Basic sentinel-header"]
    assert "sentinel-header" not in caplog.text


def test_http_when_200_rejects_spans_fails_once_without_retry(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Partial success is failure even though the upstream SDK treats HTTP 200 as success."""
    response = ExportTraceServiceResponse()
    response.partial_success.rejected_spans = 1
    capture, endpoint = server.start([Response(body=response.SerializeToString())])
    configure(monkeypatch, endpoint)
    seed_trace(db)
    assert export_failed(db)
    assert len(capture.paths) == 1


@pytest.mark.parametrize("status", [204, 302, 400])
def test_http_when_status_is_not_200_fails_without_successful_retry(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """204 and 302 are not success; 400 is never retried."""
    capture, endpoint = server.start([Response(status=status)])
    configure(monkeypatch, endpoint)
    seed_trace(db)
    assert export_failed(db)
    assert len(capture.paths) == 1


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_http_when_transient_status_receives_retry_after_then_succeeds(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """The fixed SDK retries only bounded transient statuses and honors Retry-After."""
    capture, endpoint = server.start(
        [Response(status=status, retry_after="0"), Response(status=200)]
    )
    configure(monkeypatch, endpoint)
    seed_trace(db)
    assert export_traces(db) == 2
    assert len(capture.paths) == 2


def test_http_when_retry_is_exhausted_fails_without_overall_success(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permanently unavailable collector cannot produce an accepted count."""
    capture, endpoint = server.start([Response(status=503, retry_after="0")])
    configure(monkeypatch, endpoint)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "0.01")
    seed_trace(db)
    assert export_failed(db)
    assert 1 <= len(capture.paths) <= 6


def test_http_when_protobuf_is_malformed_fails(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A syntactically invalid success response is not accepted."""
    capture, endpoint = server.start([Response(body=b"not-protobuf")])
    configure(monkeypatch, endpoint)
    seed_trace(db)
    assert export_failed(db)
    assert len(capture.paths) == 1


def test_http_when_no_traces_sends_no_request(
    db: Database, server: type[Capture], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero selected traces produce zero spans and no empty request."""
    capture, endpoint = server.start([Response()])
    configure(monkeypatch, endpoint)
    assert export_traces(db) == 0
    assert capture.paths == []
