# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real HTTP OTLP response, retry, and partial-success checks."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from datakeel.core.errors import ExecutionError
from datakeel.core.harness_models import BudgetRequest, TokenSegment, TokenUsage, TraceInput
from datakeel.harness.otel import export_traces
from datakeel.harness.service import reserve, settle
from datakeel.persistence import migrate
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


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
        self.bodies: list[bytes] = []
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
                capture.bodies.append(self.rfile.read(length))
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


def seed_trace(db: Database, conversation: str = "fixture") -> None:
    """Persist one measured conversation call through the normal metering path."""
    reservation = reserve(
        db,
        BudgetRequest(
            conversation_id=conversation,
            model="fake-script",
            input_tokens=100,
            max_output_tokens=20,
        ),
    )
    settle(
        db,
        reservation.id,
        TraceInput(
            conversation_id=conversation,
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


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed module entry point without calling the exporter in process."""
    return subprocess.run(  # noqa: S603  # Fixed local interpreter and command arguments.
        [sys.executable, "-m", "datakeel.cli", "export-traces", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def sqlite_facts(path: Path) -> tuple[str, ...]:
    """Capture durable traces, budgets, and schema through an independent read-only connection."""
    queries = (
        "SELECT * FROM model_call_trace ORDER BY id",
        "SELECT * FROM budget_accounts ORDER BY key",
        "SELECT * FROM budget_reservations ORDER BY id",
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name",
    )
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        return tuple(str(connection.execute(query).fetchall()) for query in queries)


def test_cli_when_sqlite_is_read_only_exports_filtered_spans_without_side_effects(
    tmp_path: Path, server: type[Capture], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real CLI reads existing settled facts and leaves their SQLite storage untouched."""
    home = tmp_path / "cli-home"
    home.mkdir()
    path = home / "datakeel.db"
    database = Database(f"sqlite:///{path}")
    migrate(database)
    seed_trace(database)
    seed_trace(database, conversation="other")
    database.engine.dispose()
    facts_before = sqlite_facts(path)
    files_before = sorted(entry.name for entry in home.iterdir())
    capture, endpoint = server.start([Response()])
    configure(monkeypatch, endpoint)
    monkeypatch.setenv("DATAKEEL_HOME", str(home))

    completed = run_cli("--conversation-id", "fixture")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "2 spans\n"
    assert capture.paths == ["/v1/traces"]
    request = ExportTraceServiceRequest.FromString(capture.bodies[0])
    exported = [
        span
        for resource in request.resource_spans
        for scope in resource.scope_spans
        for span in scope.spans
    ]
    assert len(exported) == 2
    by_name = {span.name: span for span in exported}
    root = by_name["datakeel.accounting_group"]
    child = by_name["chat fake-script"]
    assert root.parent_span_id == b""
    assert child.parent_span_id == root.span_id
    assert child.trace_id == root.trace_id
    assert (
        next(
            attribute.value.string_value
            for attribute in child.attributes
            if attribute.key == "gen_ai.conversation.id"
        )
        == "fixture"
    )
    assert sqlite_facts(path) == facts_before
    assert sorted(entry.name for entry in home.iterdir()) == files_before


@pytest.mark.parametrize("empty_file", [False, True], ids=["missing-file", "missing-schema"])
def test_cli_when_sqlite_is_missing_or_unmigrated_fails_without_creating_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, empty_file: bool
) -> None:
    """The real CLI reports missing storage and never creates a database or schema."""
    home = tmp_path / "missing-home"
    path = home / "datakeel.db"
    if empty_file:
        home.mkdir()
        path.touch()
    monkeypatch.setenv("DATAKEEL_HOME", str(home))

    completed = run_cli()

    assert completed.returncode != 0
    assert "run datakeel migrate first" in completed.stderr
    if empty_file:
        assert path.read_bytes() == b""
        assert sorted(entry.name for entry in home.iterdir()) == ["datakeel.db"]
    else:
        assert not home.exists()
