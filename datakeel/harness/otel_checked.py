# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Checked OTLP transport and synchronous span delivery with no ignored results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.protobuf.message import DecodeError
from opentelemetry.exporter.http.transport._requests import RequestsHTTPTransport
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    import requests
    from opentelemetry.context import Context
    from opentelemetry.exporter.http.transport._base import BaseHTTPResult

_BATCH_SIZE = 256
_HTTP_OK = 200


class CheckedOTLPTransport(RequestsHTTPTransport):
    """Bind success to HTTP 200 and an OTLP response with zero rejected spans."""

    def __init__(self, *, session: requests.Session | None = None) -> None:
        """Use the fixed exporter transport while retaining only non-sensitive failures."""
        super().__init__(session=session)
        self.failure: str | None = None

    def begin(self) -> None:
        """Clear the previous batch before serialization or network activity."""
        self.failure = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        data: bytes | None = None,
    ) -> BaseHTTPResult:
        """Inspect every real response without logging bodies or credentials."""
        self.failure = None
        result = super().request(method, url, headers=headers, timeout=timeout, data=data)
        if result.status_code != _HTTP_OK:
            self.failure = f"OTLP HTTP status {result.status_code}"
            return result
        if not result.content():
            return result
        response = ExportTraceServiceResponse()
        try:
            response.ParseFromString(result.content())
        except DecodeError:
            self.failure = "OTLP response was not valid protobuf"
            return result
        rejected = response.partial_success.rejected_spans
        if rejected:
            self.failure = f"OTLP collector rejected {rejected} spans"
        return result


class CheckedOTLPSpanExporter(OTLPSpanExporter):
    """Convert upstream result blindness into an explicit export failure."""

    def __init__(self, *, transport: CheckedOTLPTransport | None = None) -> None:
        """Use the fixed 1.45.1 custom-transport adapter boundary."""
        self._checked_transport = transport or CheckedOTLPTransport()
        super().__init__(_transport=self._checked_transport)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Require both the exporter result and the checked HTTP response to succeed."""
        self._checked_transport.begin()
        result = super().export(spans)
        if result is not SpanExportResult.SUCCESS or self._checked_transport.failure is not None:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS


class CheckedSpanProcessor(SpanProcessor):
    """Export bounded synchronous batches and retain every failure for the caller."""

    def __init__(self, exporter: SpanExporter) -> None:
        """Keep at most one 256-span batch pending and no background queue."""
        self._exporter = exporter
        self._pending: list[ReadableSpan] = []
        self._shutdown = False
        self._failed = False
        self.ended = 0
        self.accepted = 0

    @property
    def failed(self) -> bool:
        """Report any exporter, lifecycle, or dropped-span failure."""
        return self._failed or self.accepted != self.ended

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """Take no action when a span starts."""

    def on_end(self, span: ReadableSpan) -> None:
        """Account for every ended span, including calls made after shutdown."""
        self.ended += 1
        if self._shutdown:
            self._failed = True
            return
        self._pending.append(span)
        if len(self._pending) == _BATCH_SIZE:
            self._export_pending()

    def _export_pending(self) -> None:
        batch = tuple(self._pending)
        self._pending.clear()
        if not batch:
            return
        try:
            result = self._exporter.export(batch)
        except Exception:  # noqa: BLE001  # Export failure must be returned to the caller.
            self._failed = True
            return
        if result is SpanExportResult.SUCCESS:
            self.accepted += len(batch)
        else:
            self._failed = True

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the final partial batch synchronously and expose all failures."""
        del timeout_millis
        self._export_pending()
        return not self.failed

    def shutdown(self) -> None:
        """Flush once, then close the exporter while preserving shutdown failures."""
        if self._shutdown:
            return
        self._export_pending()
        self._shutdown = True
        try:
            self._exporter.shutdown()
        except Exception:  # noqa: BLE001  # Shutdown failure must not be swallowed.
            self._failed = True
