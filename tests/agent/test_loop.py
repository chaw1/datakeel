# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Loop limits and provider failures preserve durable model and budget evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.harness_models import BudgetLimits, TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.core.settings import Settings
from datakeel.harness.service import list_accounts, list_traces
from datakeel.runtime.chat_provider import model_provider
from datakeel.storage.tool_invocations import list_invocations
from tests.agent.test_service import action_script

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


@pytest.mark.parametrize(
    ("calls", "reason"),
    [
        ([ToolCall(name="list_datasets")] * 3, "repeated_call"),
        ([ToolCall(name="list_datasets"), ToolCall(name="search_files")] * 2, "ping_pong"),
        (
            [
                ToolCall(name="missing", arguments=JsonDocument({"attempt": value}))
                for value in range(3)
            ],
            "tool_failures",
        ),
    ],
)
def test_loop_when_tool_progress_guard_trips_records_reason_and_call_traces(
    db: Database,
    calls: list[ToolCall],
    reason: str,
) -> None:
    """End controlled execution with the exact detector reason and one trace per model call."""
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([ModelResponse(tool_calls=[call]) for call in calls])
    events = list(
        send_message(db, conversation.id, MessageInput(content="exercise guard"), provider=provider)
    )
    assert events[-2].stop_reason == reason
    traces = list_traces(db, conversation.id)
    assert len(traces) == len(calls)
    assert all(
        sum(part.tokens for part in trace.segments) == trace.usage.input_tokens for trace in traces
    )


def test_loop_when_empty_or_maximum_turns_reached_stops_with_distinct_reason(db: Database) -> None:
    """Differentiate stalled empty replies from a configured model-call limit."""
    for maximum, reason in [(3, "no_progress"), (1, "max_turns")]:
        conversation = create_conversation(db, ConversationCreate(max_turns=maximum))
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="empty"),
                provider=FakeProvider([ModelResponse()] * 3),
            )
        )
        assert events[-2].stop_reason == reason


def test_loop_when_budget_unavailable_stops_before_provider_call(db: Database) -> None:
    """Reject a reservation before any potentially billable provider operation."""
    conversation = create_conversation(
        db, ConversationCreate(budget=BudgetLimits(conversation_tokens=0))
    )
    provider = FakeProvider([])
    events = list(
        send_message(db, conversation.id, MessageInput(content="budget"), provider=provider)
    )
    assert events[-2].stop_reason == "budget_exceeded"
    assert provider.requests == []
    assert list_traces(db, conversation.id) == []


def test_loop_when_provider_fails_records_unknown_usage_and_accounts_reservation(
    db: Database,
) -> None:
    """Count failed HTTP requests without inventing provider token usage or final answers."""
    conversation = create_conversation(db, ConversationCreate())
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(500)), trust_env=False
        ) as client,
        model_provider(
            ConversationCreate(provider="openai"),
            Settings(openai_api_key="fixture", openai_base_url="https://fixture.invalid"),
            client,
        ) as provider,
    ):
        events = list(
            send_message(db, conversation.id, MessageInput(content="request"), provider=provider)
        )
    assert events[-2].stop_reason == "provider_error"
    trace = list_traces(db, conversation.id)[0]
    assert trace.stop_reason == "provider_error"
    assert trace.usage.input_tokens == trace.usage.output_tokens == 0
    assert trace.billing_status == "unknown"
    assert trace.accounted_tokens > 0


def test_loop_when_timeouts_repeat_consumes_budget_without_inventing_provider_usage(
    db: Database,
) -> None:
    """Prevent failed remote requests from retrying forever against a free budget."""
    conversation = create_conversation(
        db, ConversationCreate(budget=BudgetLimits(conversation_tokens=25_000))
    )
    requests: list[httpx.Request] = []

    def timeout(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        msg = "Fixture timed out after dispatch"
        raise httpx.ReadTimeout(msg, request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(timeout), trust_env=False) as client,
        model_provider(
            ConversationCreate(provider="openai"),
            Settings(openai_api_key="fixture", openai_base_url="https://fixture.invalid"),
            client,
        ) as provider,
    ):
        for _ in range(10):
            events = list(
                send_message(db, conversation.id, MessageInput(content="retry"), provider=provider)
            )
            if events[-2].stop_reason == "budget_exceeded":
                break
    assert events[-2].stop_reason == "budget_exceeded"
    traces = list_traces(db, conversation.id)
    assert len(traces) == len(requests) > 0
    assert all(
        trace.billing_status == "unknown" and trace.usage == TokenUsage() for trace in traces
    )
    account = next(item for item in list_accounts(db) if item.key.startswith("conversation:"))
    assert account.used_tokens == sum(trace.accounted_tokens for trace in traces) > 0
    assert account.reserved_tokens == 0


def test_loop_when_observed_usage_exceeds_budget_stops_before_tool_dispatch(db: Database) -> None:
    """Retain authoritative overage evidence while preventing any returned tool from running."""
    conversation = create_conversation(db, ConversationCreate())
    response = ModelResponse(
        tool_calls=[ToolCall(name="list_datasets")],
        usage=TokenUsage(input_tokens=1_000_001, output_tokens=1),
    )
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="overage"), provider=FakeProvider([response])
        )
    )
    assert events[-2].stop_reason == "budget_exceeded"
    assert not any(event.event == "tool_call" for event in events)
    assert list_invocations(db) == []
    trace = list_traces(db, conversation.id)[0]
    assert trace.budget_exceeded
    assert trace.usage == response.usage
    assert trace.accounted_tokens == 1_000_002


def test_loop_when_plan_stops_batch_preserves_matching_results_for_unexecuted_calls(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Fill skipped calls after an irreversible plan so the next provider exchange stays valid."""
    script = action_script(dataset.id, "delete_files")
    script[1] = script[1].model_copy(
        update={"tool_calls": [*script[1].tool_calls, ToolCall(name="list_datasets")]}
    )
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="delete"), provider=FakeProvider(script)
        )
    )
    assert events[-2].stop_reason == "approval_required"
    assert get_conversation(db, conversation.id).messages[-1].name == "list_datasets"
    assert "approval_required" in get_conversation(db, conversation.id).messages[-1].content
