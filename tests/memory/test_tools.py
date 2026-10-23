# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The deferred writer validates input, binds provenance and avoids content echoes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.tools import ToolCatalog, deferred_tools, resident_tools
from datakeel.core.agent_models import ConversationCreate, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.memory.service import list_memories
from datakeel.memory.tools import invoke_memory, memory_tool
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.conversation_store import create
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_invoke_memory_when_replayed_writes_once_and_preserves_source_without_content_echo(
    db: Database,
) -> None:
    """A replayed tool call cannot duplicate a memory even before invocation audit is completed."""
    session = create(db, ConversationCreate())
    call = ToolCall(name="write_memory", arguments=JsonDocument({"content": "revenue metric"}))
    context = ToolCallContext(session_id=session.id)
    first = invoke_memory(db, call, context)
    assert first.status == "SUCCEEDED"
    assert invoke_memory(db, call, context) == first
    assert len(list_memories(db)) == 1
    assert list_memories(db)[0].source_conversation_ids == [session.id]
    assert "revenue" not in first.content.model_dump_json()
    assert memory_tool().name == "write_memory"


def test_invoke_memory_when_malformed_or_unknown_scope_returns_failed_outcome(db: Database) -> None:
    """Both schema and domain failures stay inside the normal tool error contract."""
    for arguments in ({}, {"content": "revenue metric", "dataset_id": "missing"}):
        result = invoke_memory(
            db,
            ToolCall(name="write_memory", arguments=JsonDocument.model_validate(arguments)),
            ToolCallContext(),
        )
        assert result.status == "FAILED"
    assert list_memories(db) == []


def test_memory_catalog_when_discovered_allows_once_and_replays_durable_tool_result(
    db: Database,
) -> None:
    """The writer requires discovery and replay leaves both memory and invocation counts fixed."""
    conversation = create(db, ConversationCreate())
    catalog = ToolCatalog(conversation)
    context = ToolCallContext(session_id=conversation.id)
    assert "write_memory" not in {item.name for item in resident_tools()}
    assert "write_memory" in {item.name for item in deferred_tools()}
    call = ToolCall(name="write_memory", arguments=JsonDocument({"content": "revenue metric"}))
    assert catalog.invoke(db, call, context).status == "FAILED"
    catalog.invoke(
        db,
        ToolCall(name="tool_search", arguments=JsonDocument({"query": "write_memory"})),
        context,
    )
    loaded = ToolCall(name="write_memory", arguments=call.arguments)
    result = catalog.invoke(db, loaded, context)
    assert result.status == "SUCCEEDED"
    assert catalog.invoke(db, loaded, context) == result
    assert len(list_memories(db)) == 1
    assert len(list_invocations(db)) == 3
