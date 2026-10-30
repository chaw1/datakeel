# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The Agent dialog hands sentences to the planner without changing scripted conversations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelResponse,
    ScriptedResponse,
)
from datakeel.core.intent_models import PageContext
from datakeel.intents.chains import advance_chain
from datakeel.intents.model_parse import AGENT_NAME
from datakeel.storage.harness_service import list_traces
from tests.intents.support import SETUP, images

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.agent.models import AgentEvent
    from datakeel.storage.database import Database

LABELS = "Create a vehicle label set with car and truck"


def _planner(payload: dict[str, object]) -> ScriptedResponse:
    return ScriptedResponse(agent=AGENT_NAME, content=json.dumps(payload))


def _send(
    db: Database,
    conversation_id: str,
    text: str,
    provider: FakeProvider | None,
    context: PageContext | None = None,
) -> list[AgentEvent]:
    request = MessageInput(content=text, context=context)
    return list(send_message(db, conversation_id, request, provider=provider))


def test_scripted_model_plan_becomes_a_chain_and_nothing_runs(db: Database) -> None:
    """A model-proposed write is checked, stored as a chain and left for a person."""
    conversation = create_conversation(db, ConversationCreate())
    labels = [{"id": "car", "name": "car"}, {"id": "truck", "name": "truck"}]
    step = {
        "id": "s1",
        "action": "create_label_set",
        "params": {"name": "Vehicles", "labels": labels},
    }
    provider = FakeProvider([_planner({"kind": "plan", "steps": [step]})])
    events = _send(db, conversation.id, LABELS, provider)
    intent = next(event for event in events if event.event == "intent")
    assert intent.intent is not None
    assert intent.intent.kind == "plan"
    assert intent.intent.parser == "model"
    assert intent.intent.chain is not None
    assert intent.intent.chain.steps[0].params["labels"] == labels
    assert provider.requests[0].agent_name == AGENT_NAME
    assert service.list_runs(db) == []
    traces = [trace for trace in list_traces(db, conversation.id) if trace.call_type]
    assert [trace.call_type for trace in traces] == ["intent_classifier"]
    view = get_conversation(db, conversation.id)
    assert any(event.intent is not None for event in view.events)
    assert view.messages[-1].role == "assistant"


def test_conversation_view_reflects_chain_progress_after_confirmation(db: Database) -> None:
    """After a person runs the chain, the transcript card shows the receipts."""
    conversation = create_conversation(db, ConversationCreate())
    labels = [{"id": "car", "name": "car"}]
    step = {"id": "s1", "action": "create_label_set", "params": {"name": "V", "labels": labels}}
    events = _send(
        db, conversation.id, LABELS, FakeProvider([_planner({"kind": "plan", "steps": [step]})])
    )
    chain = next(event.intent.chain for event in events if event.intent and event.intent.chain)
    assert chain is not None
    advance_chain(db, chain.id, "local")
    view = get_conversation(db, conversation.id)
    shown = next(event.intent for event in view.events if event.intent is not None)
    assert shown is not None
    assert shown.chain is not None
    assert shown.chain.status == "succeeded"
    assert shown.chain.steps[0].run_ids


def test_planner_none_leaves_the_turn_to_the_free_conversation(db: Database) -> None:
    """When nothing registered fits, the next scripted response answers as before."""
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([_planner({"kind": "none"}), ModelResponse(content="Hello there.")])
    events = _send(db, conversation.id, "hello", provider)
    assert not [event for event in events if event.event == "intent"]
    assert any(event.event == "text" and event.text == "Hello there." for event in events)


def test_scripts_without_a_planner_entry_never_reach_the_planner(db: Database) -> None:
    """Existing scripted conversations keep their exact responses even for recipe sentences."""
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([ModelResponse(content="Scripted reply.")])
    events = _send(db, conversation.id, SETUP, provider)
    assert not [event for event in events if event.event == "intent"]
    assert provider.requests[0].agent_name != AGENT_NAME


def test_rules_handle_recipe_sentences_and_drop_the_unused_planner_entry(
    db: Database, tmp_path: Path
) -> None:
    """A recipe sentence is planned by rules; the scripted planner response is not sent."""
    dataset = images(db, tmp_path / "images")
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([_planner({"kind": "none"})])
    events = _send(db, conversation.id, SETUP, provider, PageContext(dataset_id=dataset.id))
    intent = next(event.intent for event in events if event.intent is not None)
    assert intent.parser == "rules"
    assert intent.chain is not None
    assert provider.requests == []
    assert provider.script == []


def test_demo_provider_plans_recipes_offline(db: Database, tmp_path: Path) -> None:
    """The offline demo configuration plans recipe sentences without any model."""
    dataset = images(db, tmp_path / "images")
    conversation = create_conversation(db, ConversationCreate())
    events = _send(db, conversation.id, SETUP, None, PageContext(dataset_id=dataset.id))
    intent = next(event.intent for event in events if event.intent is not None)
    assert intent.kind == "plan"
    assert service.list_runs(db) == []


def test_messages_without_page_context_keep_the_free_conversation(
    db: Database, tmp_path: Path
) -> None:
    """API clients that send no page context see exactly the earlier behaviour."""
    images(db, tmp_path / "images")
    conversation = create_conversation(db, ConversationCreate())
    events = _send(db, conversation.id, SETUP, None)
    assert not [event for event in events if event.event == "intent"]


def test_model_cannot_invent_identities_or_actions(db: Database, tmp_path: Path) -> None:
    """An invented dataset becomes a question; an unregistered action is refused."""
    images(db, tmp_path / "images")
    conversation = create_conversation(db, ConversationCreate())
    invented = {
        "id": "s1",
        "action": "create_project",
        "params": {"name": "X", "dataset_id": "made-up", "label_set_id": "nope"},
    }
    provider = FakeProvider(
        [
            _planner({"kind": "plan", "steps": [invented]}),
            _planner({"kind": "plan", "steps": [{"id": "s1", "action": "drop_everything"}]}),
        ]
    )
    asked = _send(db, conversation.id, "make a project from made-up", provider)
    question = next(event.intent for event in asked if event.intent is not None)
    assert question.kind == "clarify"
    refused = _send(db, conversation.id, "drop everything now please, all of it", provider)
    refusal = next(event.intent for event in refused if event.intent is not None)
    assert refusal.kind == "refuse"
    assert service.list_runs(db) == []
