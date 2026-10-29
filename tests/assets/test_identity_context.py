# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named runtime sessions cannot inherit local's protected history or memory grants."""

from pathlib import Path

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation
from datakeel.api.app import create_app
from datakeel.core.agent_models import ChatMessage, Conversation, ConversationCreate, ModelResponse
from datakeel.core.errors import AuthorizationError
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import AssetRef, JsonDocument, new_id
from datakeel.memory.service import create_memory, select_memories
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.conversation_store import get, store
from datakeel.storage.data_asset_context import (
    project_agent_history,
    read_agent_histories,
    require_agent_history,
)
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.identity_sessions import bind_session_actor
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish

MARKER = "protected-derived-record-74139"


def _dataset(db: Database, tmp_path: Path) -> str:
    file = tmp_path / "fixture.txt"
    file.write_text("Generated protected identity fixture.")
    dataset = import_paths(db, "Generated protected fixture", [file])
    asset = publish(db, AssetRef(asset_id=dataset.id))
    assert grant(db, asset, "valid", "query", subject="local")
    return dataset.id


def _register(db: Database) -> None:
    plan = prepare_action(
        db,
        "manage_users",
        JsonDocument({"request_id": new_id(), "operation": "create", "user_id": "local"}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_history_projection_and_cached_replay_use_session_actor_grants(
    db: Database, tmp_path: Path
) -> None:
    """Only the local owner can retain derived facts protected by local's query grant."""
    dataset_id = _dataset(db, tmp_path)
    originals: list[Conversation] = []
    for actor in ("local", "unknown"):
        conversation = store(
            db,
            Conversation(
                id=f"history-{actor}",
                config=ConversationCreate(),
                messages=[
                    ChatMessage(role="user", content="Question"),
                    ChatMessage(role="assistant", content=MARKER),
                ],
            ),
        )
        outcome = invoke_tool(
            db,
            "search_files",
            JsonDocument({"dataset_id": dataset_id}),
            ToolCallContext(session_id=conversation.id),
        )
        assert outcome.status == "SUCCEEDED"
        bind_session_actor(db, conversation.id, actor)
        originals.append(conversation)
    projected = read_agent_histories(db, originals)
    assert MARKER in projected[0].model_dump_json()
    assert MARKER not in projected[1].model_dump_json()
    assert project_agent_history(db, originals[1]).messages == [
        ChatMessage(role="user", content="Question")
    ]
    with pytest.raises(AuthorizationError):
        require_agent_history(db, originals[1].id)
    assert MARKER in get(db, originals[1].id).model_dump_json()


def test_named_model_and_http_memory_reads_do_not_borrow_local_grants(
    db: Database, tmp_path: Path
) -> None:
    """Protected memory stays absent from named model prompts and HTTP memory responses."""
    dataset_id = _dataset(db, tmp_path)
    protected = create_memory(
        db, MemoryCreate(content=f"shipment quarterly {MARKER}", dataset_id=dataset_id)
    )
    create_memory(db, MemoryCreate(content="Shared preference"))
    assert MARKER in select_memories(db, MARKER, dataset_id).text
    assert MARKER not in select_memories(db, MARKER, dataset_id, actor="unknown").text
    _register(db)
    conversation = create_conversation(
        db, ConversationCreate(dataset_id=dataset_id), actor="unknown"
    )
    provider = FakeProvider([ModelResponse(content="Read complete.")])
    app = create_app(db)
    app.state.agent_provider = provider
    with TestClient(app) as client:
        headers = {"X-Datakeel-Actor": "unknown"}
        listing = client.get("/api/agent/memories", headers=headers)
        assert listing.status_code == 200, listing.text
        assert MARKER not in listing.text
        assert client.get(f"/api/agent/memories/{protected.id}", headers=headers).status_code == 403
        assert (
            MARKER
            in client.get(
                f"/api/agent/memories/{protected.id}", headers={"X-Datakeel-Actor": "local"}
            ).text
        )
        response = client.post(
            f"/api/agent/conversations/{conversation.id}/messages",
            json={"content": "shipment quarterly"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    assert provider.requests
    assert all(MARKER not in request.model_dump_json() for request in provider.requests)
