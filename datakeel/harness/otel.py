# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export persisted model calls with pinned OTel GenAI and OpenInference attributes."""

from __future__ import annotations

import math
import os
from collections import defaultdict
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from sqlalchemy.exc import SQLAlchemyError

from datakeel import __version__
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.harness.otel_checked import CheckedOTLPSpanExporter, CheckedSpanProcessor
from datakeel.storage.harness_service import list_traces

if TYPE_CHECKING:
    from collections.abc import Iterable

    from datakeel.core.harness_models import ModelCallTrace
    from datakeel.storage.database import Database

_ERROR_TYPES = {
    "provider_error": "provider_error",
    "extractor_error": "provider_error",
    "transcription_error": "provider_error",
    "parse_failure": "parse_failure",
    "decode_error": "parse_failure",
    "timeout": "timeout",
    "quota": "quota_exceeded",
    "recording_error": "recording_error",
    "error": "unknown",
}
_ATTRIBUTE_TYPES = str | int | float | bool | list[str]
_CONVERSATION_CALLS = {"conversation", "intent_classifier"}
_RUN_CALLS = {"extraction", "transcription"}


def _nanoseconds(milliseconds: float) -> int:
    return round(milliseconds * 1_000_000)


def _times(item: ModelCallTrace) -> tuple[int, int]:
    end = round(item.created_at.timestamp() * 1_000_000_000)
    return max(0, end - _nanoseconds(item.latency_ms)), end


def _identity_attributes(item: ModelCallTrace) -> dict[str, _ATTRIBUTE_TYPES]:
    group = item.accounting_conversation_id or item.conversation_id
    attributes: dict[str, _ATTRIBUTE_TYPES] = {
        "datakeel.trace.id": item.id,
        "datakeel.reservation.id": item.reservation_id,
        "datakeel.call_type": item.call_type,
        "datakeel.turn": item.turn,
        "datakeel.agent_path": item.agent_path,
        "datakeel.depth": item.depth,
        "datakeel.tool_calls": item.tool_calls,
        "datakeel.cost_usd": float(item.cost_usd),
        "datakeel.price_version": item.price_version,
        "datakeel.budget_exceeded": item.budget_exceeded,
        "datakeel.billing_status": item.billing_status,
        "datakeel.accounted_tokens": item.accounted_tokens,
        "datakeel.accounting_conversation_id": group,
        "datakeel.stop_reason": item.stop_reason,
    }
    if item.parent_tool_call_id is not None:
        attributes["datakeel.parent_tool_call_id"] = item.parent_tool_call_id
    if item.call_type in _CONVERSATION_CALLS:
        attributes["gen_ai.conversation.id"] = item.conversation_id
        attributes["session.id"] = item.conversation_id
    elif item.call_type in _RUN_CALLS:
        key = "datakeel.plan.id" if item.agent_path == "label_drafts" else "datakeel.run.id"
        attributes[key] = item.conversation_id
    return attributes


def _attributes(item: ModelCallTrace) -> dict[str, _ATTRIBUTE_TYPES]:
    attributes = _identity_attributes(item)
    attributes.update(
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": item.provider,
            "gen_ai.request.model": item.model,
            "openinference.span.kind": "LLM",
            "llm.model_name": item.model,
        }
    )
    usage = item.observed_usage or item.usage
    if item.billing_status == "actual" or item.observed_usage is not None:
        attributes.update(
            {
                "gen_ai.usage.input_tokens": usage.input_tokens,
                "gen_ai.usage.output_tokens": usage.output_tokens,
                "llm.token_count.prompt": usage.input_tokens,
                "llm.token_count.completion": usage.output_tokens,
            }
        )
    if usage.cache_read_tokens > 0:
        attributes["gen_ai.usage.cache_read.input_tokens"] = usage.cache_read_tokens
        attributes["llm.token_count.prompt_details.cache_read"] = usage.cache_read_tokens
    if usage.cache_write_tokens > 0:
        attributes["gen_ai.usage.cache_write.input_tokens"] = usage.cache_write_tokens
    if item.stop_reason:
        error_type = _ERROR_TYPES.get(item.stop_reason)
        attributes["gen_ai.response.finish_reasons"] = [
            "error" if error_type is not None else item.stop_reason
        ]
    return attributes


def _end_child(tracer: Tracer, item: ModelCallTrace, parent: trace.Span) -> tuple[int, int]:
    start, end = _times(item)
    context = trace.set_span_in_context(parent)
    span = tracer.start_span(
        f"chat {item.model}",
        context=context,
        kind=SpanKind.CLIENT,
        attributes=_attributes(item),
        start_time=start,
    )
    error_type = _ERROR_TYPES.get(item.stop_reason)
    if error_type is not None:
        span.set_status(Status(StatusCode.ERROR, error_type))
        span.set_attribute("error.type", error_type)
    span.end(end_time=end)
    return start, end


def _record_group(tracer: Tracer, items: Iterable[ModelCallTrace]) -> None:
    group = tuple(items)
    group_id = group[0].accounting_conversation_id or group[0].conversation_id
    intervals = [_times(item) for item in group]
    root = tracer.start_span(
        "datakeel.accounting_group",
        kind=SpanKind.INTERNAL,
        attributes={"datakeel.accounting_conversation_id": group_id},
        start_time=min(start for start, _ in intervals),
    )
    for item in group:
        _end_child(tracer, item, root)
    root.end(end_time=max(end for _, end in intervals))


def _groups(traces: Iterable[ModelCallTrace]) -> list[tuple[ModelCallTrace, ...]]:
    grouped: dict[str, list[ModelCallTrace]] = defaultdict(list)
    for item in traces:
        grouped[item.accounting_conversation_id or item.conversation_id].append(item)
    return [tuple(grouped[key]) for key in sorted(grouped)]


def _validate_protocol() -> None:
    # The official SDK owns these unprefixed variables at its adapter boundary.
    for name in ("OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"):
        value = os.environ.get(name)
        if value is not None and value.strip().lower() != "http/protobuf":
            msg = f"{name} must be http/protobuf"
            raise ValidationError(msg)


def export_traces(db: Database, conversation_id: str | None = None) -> int:
    """Synchronously export every selected persisted trace or fail without success output."""
    _validate_protocol()
    try:
        selected = list_traces(db, conversation_id)
    except SQLAlchemyError as error:
        msg = "Trace database is missing its required schema; run datakeel migrate first"
        raise ExecutionError(msg) from error
    if not selected:
        return 0
    if not all(math.isfinite(float(item.cost_usd)) for item in selected):
        msg = "Trace cost must be finite before OTLP export"
        raise ValidationError(msg)
    exporter = CheckedOTLPSpanExporter()
    processor = CheckedSpanProcessor(exporter)
    provider = TracerProvider(
        resource=Resource.create({"service.name": "datakeel", "service.version": __version__}),
        shutdown_on_exit=False,
    )
    provider.add_span_processor(processor)
    try:
        tracer = provider.get_tracer("datakeel.harness.otel", __version__)
        for group in _groups(selected):
            _record_group(tracer, group)
        if not provider.force_flush():
            msg = "OTLP export failed; not all spans were accepted"
            raise ExecutionError(msg)
    finally:
        provider.shutdown()
    if processor.failed:
        msg = "OTLP export failed during flush or shutdown"
        raise ExecutionError(msg)
    return processor.accepted
