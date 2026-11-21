# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Search authorized conversation histories through the public HTTP endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.agent.models import AgentEvent
from datakeel.api.app import create_app
from datakeel.core.agent_models import ChatMessage, Conversation, ConversationCreate, ToolCall
from datakeel.core.intent_models import IntentResult
from datakeel.core.models import JsonDocument, new_id
from datakeel.dataset_store.dataset_service import import_paths
from datakeel.storage.conversation_store import store
from datakeel.storage.identity_sessions import bind_session_actor
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.storage.database import Database

URL = "/api/agent/conversations"


@pytest.fixture
def search_client(db: Database, tmp_path: Path) -> Iterator[tuple[TestClient, list[Conversation]]]:
    """Persist real transcripts with independent message, tool and intent search terms."""
    source = tmp_path / "generated.txt"
    source.write_text("Generated conversation search fixture.")
    datasets = [import_paths(db, name, [source]) for name in ("first", "second")]
    conversations: list[Conversation] = []
    for index, dataset in enumerate([*datasets, None]):
        conversations.append(
            store(
                db,
                Conversation(
                    id=f"session-{index}",
                    config=ConversationCreate(
                        dataset_id=dataset.id if dataset else None, model=f"model-{index}"
                    ),
                    created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
                    messages=[ChatMessage(role="user", content="Winter release Straße")]
                    if index == 1
                    else _messages()
                    if index == 0
                    else [],
                    events=[
                        JsonDocument(event.model_dump(mode="json"))
                        for event in (
                            AgentEvent(event="tool_call", call=ToolCall(name="inspect_metadata")),
                            AgentEvent(
                                event="intent",
                                intent=IntentResult(
                                    kind="answer",
                                    text="Validate invoices",
                                    request="Reconcile ledger",
                                ),
                            ),
                        )
                    ]
                    if index == 0
                    else [],
                ),
            )
        )
    with TestClient(create_app(db)) as client:
        yield client, conversations


def _messages() -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="hidden-system-marker"),
        ChatMessage(role="user", content="Winter release"),
        ChatMessage(
            role="assistant", content="Budget approved", tool_calls=[ToolCall(name="search_files")]
        ),
        ChatMessage(role="tool", content="hidden-tool-marker"),
    ]


@pytest.mark.parametrize(
    ("query", "indexes"),
    [
        ("WINTER", [0, 1]),
        ("approved", [0]),
        ("SEARCH_FILES", [0]),
        ("inspect_metadata", [0]),
        ("  release\tBUDGET\nsearch_files  ", [0]),
        ("invoices", [0]),
        ("ledger", [0]),
        ("answer", [0]),
        ("STRASSE", [1]),
        ("model-1", [1]),
        ("session-2", [2]),
        ("winter missing", []),
        ("absent", []),
        ("hidden-system-marker", []),
        ("hidden-tool-marker", []),
    ],
)
def test_search_matches_all_terms_across_supported_fields(
    search_client: tuple[TestClient, list[Conversation]], query: str, indexes: list[int]
) -> None:
    """Match case-insensitively across fields, excluding system prompts and tool payloads."""
    client, conversations = search_client
    response = client.get(URL, params={"q": query})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [conversations[i].id for i in indexes]


def test_dataset_and_combined_filters_preserve_unfiltered_response(
    search_client: tuple[TestClient, list[Conversation]],
) -> None:
    """Blank parameters preserve the exact response and dataset filters use complete IDs."""
    client, conversations = search_client
    original = client.get(URL)
    assert original.status_code == 200
    assert [item["id"] for item in original.json()] == [item.id for item in conversations]
    for params in ({"q": ""}, {"q": " \t\n", "dataset_id": "  "}, {"dataset_id": ""}):
        assert client.get(URL, params=params).json() == original.json()
    dataset_id = conversations[0].config.dataset_id
    assert dataset_id is not None
    for params, indexes in (
        ({"dataset_id": f" {dataset_id} "}, [0]),
        ({"dataset_id": "missing"}, []),
        ({"dataset_id": dataset_id[:-1]}, []),
        ({"q": dataset_id}, [0]),
        ({"q": "Winter", "dataset_id": dataset_id}, [0]),
        ({"q": "model-1", "dataset_id": dataset_id}, []),
    ):
        response = client.get(URL, params=params)
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()] == [conversations[i].id for i in indexes]


def test_search_cannot_discover_another_actors_conversation(
    db: Database, search_client: tuple[TestClient, list[Conversation]]
) -> None:
    """Apply identity selection before text or dataset matching, including exact known IDs."""
    client, conversations = search_client
    plan = prepare_action(
        db,
        "manage_users",
        JsonDocument({"request_id": new_id(), "operation": "create", "user_id": "local"}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    bind_session_actor(db, conversations[0].id, "other")
    for query in ("approved", conversations[0].id):
        denied = client.get(URL, params={"q": query})
        assert denied.status_code == 200, denied.text
        assert denied.json() == []
        own = client.get(URL, params={"q": query}, headers={"X-Datakeel-Actor": "other"})
        assert own.status_code == 200, own.text
        assert [item["id"] for item in own.json()] == [conversations[0].id]
    response = client.get(URL, params={"q": "Winter"})
    assert [item["id"] for item in response.json()] == [conversations[1].id]
    dataset_id = conversations[0].config.dataset_id
    assert dataset_id is not None
    assert client.get(URL, params={"dataset_id": dataset_id, "q": "Winter"}).json() == []
