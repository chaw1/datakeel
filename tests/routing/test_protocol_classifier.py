# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real-protocol classification remains separate from conversational context and turns."""

import json

import httpx
import pytest

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput
from datakeel.core.settings import Settings
from datakeel.harness.service import list_traces
from datakeel.runtime.chat_provider import model_provider
from datakeel.storage.database import Database
from tests.routing.protocol_helpers import ProtocolKind, successful_payload


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("classification", ["dataset-health", "unregistered-workflow"])
def test_classification_protocol_when_ambiguous_uses_session_model_and_separate_trace(
    db: Database, kind: ProtocolKind, classification: str
) -> None:
    """Keep classifier instructions separate from the normal conversation context."""
    model = "gpt-4.1-mini" if kind == "openai" else "claude-haiku-4-5-20251001"
    config = ConversationCreate(provider=kind, model=model)
    conversation = create_conversation(db, config)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == model
        calls.append(request.content.decode())
        content = classification if len(calls) == 1 else "The normal response."
        return httpx.Response(200, json=successful_payload(kind, model, content))

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        model_provider(
            config, Settings.model_validate({f"{kind}_api_key": "fixture"}), client
        ) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(
                    content="Begin with dataset health check; low-quality sample cleanup is later."
                ),
                provider=provider,
            )
        )
    assert len(calls) == 2
    assert "Select the single workflow requested first" in calls[0]
    assert "Select the single workflow requested first" not in calls[1]
    assert "The normal response." in [event.text for event in events]
    traces = list_traces(db, conversation.id)
    assert [trace.call_type for trace in traces] == ["intent_classifier", "conversation"]
    assert [trace.turn for trace in traces] == [1, 1]
    decision = next(event.route for event in events if event.route is not None)
    assert decision.workflow_id == (classification if classification == "dataset-health" else None)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_classification_protocol_when_rejected_does_not_abort_response(
    db: Database, kind: ProtocolKind
) -> None:
    """A rejected classification still permits a separately metered normal model response."""
    model = "gpt-4.1-mini" if kind == "openai" else "claude-haiku-4-5-20251001"
    config = ConversationCreate(provider=kind, model=model)
    conversation = create_conversation(db, config)
    attempts = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "fixture rejection", "type": "invalid_request_error"}},
            )
        return httpx.Response(200, json=successful_payload(kind, model))

    with (
        httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client,
        model_provider(
            config, Settings.model_validate({f"{kind}_api_key": "fixture"}), client
        ) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(
                    content="Begin with dataset health check; low-quality sample cleanup is later."
                ),
                provider=provider,
            )
        )
    assert attempts == 2
    assert events[-1].route is not None
    assert events[-1].route.branch == "free_agent"
    assert any(event.text == "Recovered response." for event in events)
