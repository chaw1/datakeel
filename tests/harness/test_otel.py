# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pinned OTel mapping and checked processor regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from sqlalchemy import text

from datakeel.core.errors import ExecutionError, NotFoundError, ValidationError
from datakeel.core.harness_models import ModelCallTrace, TokenSegment, TokenUsage
from datakeel.harness.otel import _groups, _record_group, export_traces
from datakeel.harness.otel_checked import CheckedSpanProcessor
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from pathlib import Path


class MemoryExporter(SpanExporter):
    """Capture synchronous batches without hiding export outcomes."""

    def __init__(self, result: SpanExportResult = SpanExportResult.SUCCESS) -> None:
        """Configure one deterministic export result."""
        self.result = result
        self.batches: list[tuple[ReadableSpan, ...]] = []
        self.shutdown_called = False

    def export(self, spans: tuple[ReadableSpan, ...]) -> SpanExportResult:
        """Record each complete batch."""
        self.batches.append(spans)
        return self.result

    def shutdown(self) -> None:
        """Record lifecycle cleanup."""
        self.shutdown_called = True


def trace(  # noqa: PLR0913  # Keyword-only fields keep boundary cases explicit.
    identifier: str = "call-1",
    *,
    call_type: str = "conversation",
    conversation: str = "conversation-1",
    accounting: str | None = None,
    agent_path: str = "main",
    stop_reason: str = "stop",
    billing: str = "actual",
    usage: TokenUsage | None = None,
    observed: TokenUsage | None = None,
    latency: float = 12.5,
    created_at: datetime = datetime(2026, 11, 3, tzinfo=UTC),
) -> ModelCallTrace:
    """Build a complete persisted trace fixture without a model request."""
    measured = usage or TokenUsage(input_tokens=100, output_tokens=10)
    return ModelCallTrace.model_validate(
        {
            "id": identifier,
            "reservation_id": f"reservation-{identifier}",
            "conversation_id": conversation,
            "accounting_conversation_id": accounting,
            "turn": 1,
            "model": "fake-script",
            "provider": "fake",
            "segments": [TokenSegment(name="test", tokens=measured.input_tokens)],
            "usage": measured,
            "observed_usage": observed,
            "latency_ms": latency,
            "stop_reason": stop_reason,
            "tool_calls": 1,
            "billing_status": billing,
            "call_type": call_type,
            "agent_path": agent_path,
            "depth": 0,
            "parent_tool_call_id": "parent-tool",
            "cost_usd": Decimal("0.000089"),
            "price_version": "fixture",
            "created_at": created_at,
            "accounted_tokens": 999,
            "budget_exceeded": False,
        }
    )


def export(items: list[ModelCallTrace]) -> tuple[MemoryExporter, CheckedSpanProcessor]:
    """Record groups through the real SDK and capture all resulting spans."""
    exporter = MemoryExporter()
    processor = CheckedSpanProcessor(exporter)
    provider = TracerProvider(
        resource=Resource.create({"service.name": "datakeel", "service.version": "test"}),
        active_span_processor=processor,
        shutdown_on_exit=False,
    )
    tracer = provider.get_tracer("test")
    for group in _groups(items):
        _record_group(tracer, group)
    assert provider.force_flush()
    provider.shutdown()
    return exporter, processor


def spans(
    exported: MemoryExporter | tuple[MemoryExporter, CheckedSpanProcessor],
) -> list[ReadableSpan]:
    """Flatten exported batches in occurrence order."""
    exporter = exported if isinstance(exported, MemoryExporter) else exported[0]
    return [span for batch in exporter.batches for span in batch]


def test_mapping_when_conversation_has_usage_preserves_dual_semantics_and_approximate_time() -> (
    None
):
    """A real conversation carries official session fields and dual token attributes."""
    item = trace(
        usage=TokenUsage(
            input_tokens=100, output_tokens=10, cache_read_tokens=40, cache_write_tokens=20
        )
    )
    exporter, processor = export([item])
    child, root = spans(exporter)
    assert processor.accepted == 2
    assert root.name == "datakeel.accounting_group"
    assert root.attributes is not None
    assert "gen_ai.request.model" not in root.attributes
    assert child.name == "chat fake-script"
    assert child.attributes is not None
    assert child.attributes["gen_ai.operation.name"] == "chat"
    assert child.attributes["openinference.span.kind"] == "LLM"
    assert child.attributes["gen_ai.conversation.id"] == "conversation-1"
    assert child.attributes["session.id"] == "conversation-1"
    assert child.attributes["gen_ai.usage.input_tokens"] == 100
    assert child.attributes["llm.token_count.completion"] == 10
    assert child.attributes["gen_ai.usage.cache_read.input_tokens"] == 40
    assert child.attributes["gen_ai.usage.cache_write.input_tokens"] == 20
    assert child.attributes["datakeel.accounted_tokens"] == 999
    assert child.start_time == round(item.created_at.timestamp() * 1_000_000_000) - 12_500_000
    assert child.end_time == round(item.created_at.timestamp() * 1_000_000_000)
    assert child.parent is not None
    assert child.parent.span_id == root.context.span_id


@pytest.mark.parametrize(
    ("call_type", "path", "identity_key"),
    [
        ("extraction", "main", "datakeel.run.id"),
        ("transcription", "main", "datakeel.run.id"),
        ("extraction", "label_drafts", "datakeel.plan.id"),
    ],
)
def test_mapping_when_run_or_plan_has_no_fake_official_session(
    call_type: str, path: str, identity_key: str
) -> None:
    """Run and plan IDs remain Datakeel attributes, never fabricated sessions."""
    child, _ = spans(export([trace(call_type=call_type, agent_path=path)]))
    assert child.attributes is not None
    assert child.attributes.get(identity_key) == "conversation-1"
    assert "gen_ai.conversation.id" not in child.attributes
    assert "session.id" not in child.attributes


def test_usage_when_unknown_has_observed_usage_exports_observation_not_accounted() -> None:
    """Unknown billing does not erase provider-observed extraction usage."""
    observed = TokenUsage(input_tokens=7, output_tokens=3)
    item = trace(
        call_type="extraction",
        billing="unknown",
        usage=TokenUsage(),
        observed=observed,
    )
    child, _ = spans(export([item]))
    assert child.attributes is not None
    assert child.attributes["gen_ai.usage.input_tokens"] == 7
    assert child.attributes["gen_ai.usage.output_tokens"] == 3
    assert child.attributes["datakeel.accounted_tokens"] == 999


def test_usage_when_unknown_without_observation_omits_usage_and_zero_cache() -> None:
    """No observation means no fabricated zero token usage or cache attributes."""
    item = trace(call_type="extraction", billing="unknown", usage=TokenUsage())
    child, _ = spans(export([item]))
    assert child.attributes is not None
    assert "gen_ai.usage.input_tokens" not in child.attributes
    assert "llm.token_count.prompt" not in child.attributes
    assert "gen_ai.usage.cache_read.input_tokens" not in child.attributes
    assert child.status.status_code.name == "UNSET"


def test_usage_when_actual_zero_is_known_preserves_zero_but_omits_cache() -> None:
    """A known zero is different from missing usage."""
    item = trace(usage=TokenUsage())
    child, _ = spans(export([item]))
    assert child.attributes is not None
    assert child.attributes["gen_ai.usage.input_tokens"] == 0
    assert child.attributes["gen_ai.usage.output_tokens"] == 0
    assert "gen_ai.usage.cache_read.input_tokens" not in child.attributes


@pytest.mark.parametrize(
    ("reason", "error_type"),
    [
        ("provider_error", "provider_error"),
        ("extractor_error", "provider_error"),
        ("transcription_error", "provider_error"),
        ("parse_failure", "parse_failure"),
        ("decode_error", "parse_failure"),
        ("timeout", "timeout"),
        ("quota", "quota_exceeded"),
        ("recording_error", "recording_error"),
        ("error", "unknown"),
    ],
)
def test_errors_when_reason_is_known_use_closed_low_cardinality_mapping(
    reason: str, error_type: str
) -> None:
    """Known failures set ERROR and the prescribed finish reason."""
    child, _ = spans(export([trace(stop_reason=reason)]))
    assert child.attributes is not None
    assert child.attributes["error.type"] == error_type
    assert child.attributes["gen_ai.response.finish_reasons"] == ("error",)
    assert child.status.status_code.name == "ERROR"


@pytest.mark.parametrize("reason", ["length", "truncated", "draft", "repair", "unrecognized"])
def test_errors_when_reason_is_not_known_failure_preserve_fact_without_guessing(
    reason: str,
) -> None:
    """Truncation, drafts, and unknown statuses are not automatically failures."""
    child, _ = spans(export([trace(stop_reason=reason)]))
    assert child.attributes is not None
    assert child.attributes["gen_ai.response.finish_reasons"] == (reason,)
    assert child.attributes["datakeel.stop_reason"] == reason
    assert "error.type" not in child.attributes


def test_root_times_when_input_unordered_uses_child_min_max_and_nanosecond_rounding() -> None:
    """Persisted reconstruction is deterministic for shuffled input and sub-microseconds."""
    early = trace("early", latency=0.0000015, created_at=datetime(2026, 11, 3, 0, 0, 1, tzinfo=UTC))
    late = trace("late", latency=0, created_at=datetime(2026, 11, 3, 0, 0, 2, tzinfo=UTC))
    first, second, root = spans(export([late, early]))
    assert (first.name, second.name) == ("chat fake-script", "chat fake-script")
    assert root.start_time == min(value.start_time for value in (first, second))
    assert root.end_time == max(value.end_time for value in (first, second))
    assert first.start_time == first.end_time
    assert second.start_time == second.end_time - 2


def test_groups_when_accounting_ids_differ_create_one_neutral_root_per_group() -> None:
    """Child and parent conversations remain in their own accounting groups."""
    items = [
        trace("one", conversation="child", accounting="root"),
        trace("two", conversation="other"),
    ]
    assert len(_groups(items)) == 2
    exporter, processor = export(items)
    assert processor.accepted == 4
    assert sum(span.name == "datakeel.accounting_group" for span in spans(exporter)) == 2


def test_attribute_keys_when_sensitive_fields_exist_use_exact_allowlist() -> None:
    """No prompt, route, transcript, tool payload, or exporter header can enter attributes."""
    allowed = {
        "datakeel.trace.id",
        "datakeel.reservation.id",
        "datakeel.call_type",
        "datakeel.turn",
        "datakeel.agent_path",
        "datakeel.depth",
        "datakeel.tool_calls",
        "datakeel.cost_usd",
        "datakeel.price_version",
        "datakeel.budget_exceeded",
        "datakeel.billing_status",
        "datakeel.accounted_tokens",
        "datakeel.accounting_conversation_id",
        "datakeel.stop_reason",
        "datakeel.parent_tool_call_id",
        "gen_ai.conversation.id",
        "session.id",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "openinference.span.kind",
        "llm.model_name",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "llm.token_count.prompt",
        "llm.token_count.completion",
        "gen_ai.usage.cache_read.input_tokens",
        "llm.token_count.prompt_details.cache_read",
        "gen_ai.usage.cache_write.input_tokens",
        "gen_ai.response.finish_reasons",
    }
    item = trace(
        usage=TokenUsage(
            input_tokens=100, output_tokens=10, cache_read_tokens=40, cache_write_tokens=20
        )
    )
    child, _ = spans(export([item]))
    assert child.attributes is not None
    assert set(child.attributes) == allowed
    assert "sentinel-header-value" not in repr(child.attributes)


def test_processor_when_more_than_2048_spans_exports_every_bounded_batch() -> None:
    """No SDK queue limit can silently drop the 2049th span or any later span."""
    exporter = MemoryExporter()
    processor = CheckedSpanProcessor(exporter)
    for _ in range(2051):
        processor.on_end(cast("ReadableSpan", object()))
    assert processor.force_flush()
    processor.shutdown()
    assert [len(batch) for batch in exporter.batches] == [256] * 8 + [3]
    assert processor.accepted == processor.ended == 2051
    assert exporter.shutdown_called


def test_processor_when_export_fails_or_raises_never_reports_accepted() -> None:
    """FAILURE and exceptions remain visible through flush and shutdown."""
    for result in (SpanExportResult.FAILURE,):
        exporter = MemoryExporter(result)
        processor = CheckedSpanProcessor(exporter)
        processor.on_end(cast("ReadableSpan", object()))
        assert not processor.force_flush()
        assert processor.failed
        assert processor.accepted == 0

    class RaisingExporter(MemoryExporter):
        def export(self, spans: tuple[ReadableSpan, ...]) -> SpanExportResult:
            msg = "fixture"
            raise RuntimeError(msg)

    processor = CheckedSpanProcessor(RaisingExporter())
    processor.on_end(cast("ReadableSpan", object()))
    assert not processor.force_flush()
    processor.shutdown()
    assert processor.failed


def test_processor_when_batch_partially_fails_counts_only_accepted() -> None:
    """One failed batch cannot be hidden by later successful batches."""
    exporter = MemoryExporter()
    processor = CheckedSpanProcessor(exporter)
    for _ in range(256):
        processor.on_end(cast("ReadableSpan", object()))
    exporter.result = SpanExportResult.FAILURE
    processor.on_end(cast("ReadableSpan", object()))
    assert not processor.force_flush()
    assert processor.accepted == 256
    assert processor.ended == 257


def test_read_only_database_when_file_missing_does_not_create_home_or_db(
    tmp_path: Path,
) -> None:
    """Read-only export never creates a fresh database and reports zero spans."""
    home = tmp_path / "missing"
    with pytest.raises(NotFoundError, match="run datakeel migrate"):
        Database(f"sqlite:///{home / 'state.db'}", read_only=True)
    assert not home.exists()


def test_read_only_database_when_schema_missing_fails_without_creating_tables(
    tmp_path: Path,
) -> None:
    """An existing empty file is not silently migrated."""
    path = tmp_path / "empty.db"
    path.touch()
    database = Database(f"sqlite:///{path}", read_only=True)
    try:
        with pytest.raises(ExecutionError, match="run datakeel migrate"):
            export_traces(database)
        with database.engine.connect() as connection:
            names = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
        assert names == []
    finally:
        database.engine.dispose()


def test_protocol_when_not_http_protobuf_fails_before_export(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both generic and signal-specific protocol settings are enforced."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    with pytest.raises(ValidationError, match="http/protobuf"):
        export_traces(db)
