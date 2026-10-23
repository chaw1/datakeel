# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conversation routing preserves independent billing, replay, and original event prefixes."""

from decimal import Decimal

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ModelResponse,
    ToolCall,
)
from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import BudgetLimits, TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.core.routing_models import RouteDecision
from datakeel.harness.service import list_accounts, list_traces
from datakeel.routing.classifier import OfflineClassifier, classification_request
from datakeel.storage.database import Database
from datakeel.workflows.models import WorkflowDefinition

AMBIGUOUS = "Prioritize a dataset health check; plan low-quality sample cleanup later."


def test_classification_when_ambiguous_is_independently_billed_without_turns(db: Database) -> None:
    """The classifier neither consumes the scripted queue nor counts toward max_turns."""
    conversation = create_conversation(db, ConversationCreate(model="fake-script", max_turns=1))
    provider = FakeProvider([ModelResponse(content="Response remains available.")])
    request = MessageInput(content=AMBIGUOUS)
    events = list(send_message(db, conversation.id, request, provider=provider))
    traces = list_traces(db, conversation.id)
    assert [trace.call_type for trace in traces] == ["intent_classifier", "conversation"]
    assert [trace.turn for trace in traces] == [1, 1]
    assert len(provider.requests) == 1
    assert get_conversation(db, conversation.id).turns == 1
    assert [event.event for event in events] == ["text", "route", "done"]
    assert events[-2].route is not None
    assert events[-2].route.workflow_id == "dataset-health"
    assert events[-2].route.inputs.dataset_id is None
    assert list(send_message(db, conversation.id, request, provider=provider)) == events
    assert get_conversation(db, conversation.id).events == events
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))
    assert all(trace.cost_usd > Decimal(0) for trace in traces)


@pytest.mark.parametrize(
    "content", ["Inspect a single quality score", "Run a dataset health check end to end"]
)
def test_keyword_or_free_route_when_unambiguous_adds_no_model_call(
    db: Database, content: str
) -> None:
    """Keyword suggestions preserve existing trace counts and the original model context."""
    conversation = create_conversation(db, ConversationCreate(model="fake-script"))
    provider = FakeProvider([ModelResponse(content="Completed.")])
    events = list(
        send_message(db, conversation.id, MessageInput(content=content), provider=provider)
    )
    assert len(list_traces(db, conversation.id)) == 1
    assert provider.requests[0].messages[1].content == content
    assert any(event.route is not None for event in events)


def test_classification_when_provider_fails_still_answers(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An optional classifier failure settles its reservation and falls back to free Agent."""

    def fail(_self: OfflineClassifier, _request: ModelRequest) -> ModelResponse:
        reason = "timeout"
        raise ProviderError(reason)

    monkeypatch.setattr(OfflineClassifier, "complete", fail)
    conversation = create_conversation(db, ConversationCreate(model="fake-script"))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content=AMBIGUOUS),
            provider=FakeProvider([ModelResponse(content="Still answered.")]),
        )
    )
    assert events[0].text == "Still answered."
    route = events[-1].route
    assert route is not None
    assert route.branch == "free_agent"
    assert route.reason == "classifier_unavailable:ProviderError"
    traces = list_traces(db, conversation.id)
    assert traces[0].billing_status == "unknown"
    assert traces[1].call_type == "conversation"
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))


def test_classification_when_reservation_rejected_still_answers(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Classifier budget rejection does not close the normal response path."""

    def oversized(
        model: str, text: str, decision: RouteDecision, workflows: list[WorkflowDefinition]
    ) -> ModelRequest:
        return classification_request(model, text, decision, workflows).model_copy(
            update={"max_output_tokens": 20_000}
        )

    monkeypatch.setattr("datakeel.routing.service.classification_request", oversized)
    conversation = create_conversation(
        db, ConversationCreate(model="fake-script", budget=BudgetLimits(conversation_tokens=10_000))
    )
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content=AMBIGUOUS),
            provider=FakeProvider([ModelResponse(content="Normal response.")]),
        )
    )
    assert events[0].text == "Normal response."
    assert events[-1].route is not None
    assert events[-1].route.reason == "classifier_unavailable:BudgetError"
    assert len(list_traces(db, conversation.id)) == 1


def test_model_tier_when_tool_result_occurs_then_new_response_resets(db: Database) -> None:
    """Current-response state changes tiers without leaking tool-result flags into the next turn."""
    conversation = create_conversation(db, ConversationCreate(model="fake-script"))
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(content="Available."),
        ]
    )
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="List available collections"),
            provider=provider,
        )
    )
    assert events[0].event == "tool_call"
    routes = events[-1].model_routes
    assert [route.tier for route in routes] == ["simple", "multi_step"]
    later = list(
        send_message(
            db, conversation.id, MessageInput(content="Hello again"), provider=FakeProvider([])
        )
    )
    assert later[-1].model_routes[0].tier == "simple"


def test_model_tier_when_controlled_tool_loaded_is_high_risk(db: Database) -> None:
    """Discovering an action raises risk before the model has planned an invocation."""
    conversation = create_conversation(db, ConversationCreate(model="fake-script"))
    provider = FakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(name="tool_search", arguments=JsonDocument({"query": "delete_files"}))
                ]
            ),
            ModelResponse(content="Found action."),
        ]
    )
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Discover the deletion action schema"),
            provider=provider,
        )
    )
    assert [route.tier for route in events[-1].model_routes] == [
        "simple",
        "high_risk",
    ]


def test_accounting_when_actual_usage_exceeds_budget_keeps_original_stop(db: Database) -> None:
    """Routed accounting still persists provider overruns and blocks further tool work."""
    conversation = create_conversation(
        db, ConversationCreate(model="fake-script", budget=BudgetLimits(conversation_tokens=10_000))
    )
    response = ModelResponse(
        content="Overrun", usage=TokenUsage(input_tokens=1, output_tokens=20_000)
    )
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="Hello"), provider=FakeProvider([response])
        )
    )
    assert any(event.stop_reason == "budget_exceeded" for event in events)
    assert list_traces(db, conversation.id)[0].budget_exceeded
