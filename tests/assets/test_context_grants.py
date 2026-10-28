# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Revocation removes derived data from future model context while retaining stored evidence."""

from pathlib import Path

from datakeel.core.agent_models import ChatMessage, Conversation, ConversationCreate
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.memory.service import create_memory, select_memories
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.conversation_store import get, store
from datakeel.storage.data_asset_context import project_agent_history
from datakeel.storage.database import Database
from tests.assets.entry_helpers import grant, publish, revoke, seed_resources


def test_revocation_filters_provider_history_and_attributed_memory(
    db: Database, tmp_path: Path
) -> None:
    """Derived assistant prose and source-linked memory cannot outlive its original grant."""
    resources = seed_resources(db, tmp_path)
    asset = publish(db, AssetRef(asset_id=resources.dataset_id))
    grant_id = grant(db, asset, "valid", "query")
    assert grant_id
    conversation = store(
        db,
        Conversation(
            id="source-conversation",
            config=ConversationCreate(),
            messages=[
                ChatMessage(role="user", content="shipment quarterly question"),
                ChatMessage(role="assistant", content="private derived value 84621"),
            ],
        ),
    )
    outcome = invoke_tool(
        db,
        "search_files",
        JsonDocument({"dataset_id": resources.dataset_id}),
        ToolCallContext(session_id=conversation.id),
    )
    assert outcome.status == "SUCCEEDED"
    for body in (
        MemoryCreate(content="shipment quarterly scoped 84621", dataset_id=resources.dataset_id),
        MemoryCreate(
            content="shipment quarterly source 84621", source_conversation_id=conversation.id
        ),
        MemoryCreate(content="shipment quarterly user preference"),
    ):
        create_memory(db, body)
    assert len(select_memories(db, "shipment quarterly", resources.dataset_id).entries) == 3
    assert project_agent_history(db, conversation) == conversation
    revoke(db, grant_id)
    projected = project_agent_history(db, conversation)
    assert [message.role for message in projected.messages] == ["user"]
    assert "84621" not in projected.model_dump_json()
    assert get(db, conversation.id) == conversation
    selected = select_memories(db, "shipment quarterly", resources.dataset_id)
    assert len(selected.entries) == 1
    assert "user preference" in selected.text
    assert "84621" not in selected.text
