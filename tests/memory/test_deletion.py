# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hard deletion remains effective across fresh model contexts and archived provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse
from datakeel.core.memory_models import MemoryCreate
from datakeel.memory.service import create_memory, delete_memory, list_memories, retrieve
from datakeel.storage.memory_rows import MemoryRow
from tests.memory.helpers import entry

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_delete_memory_when_retrieved_excludes_it_from_new_conversation(db: Database) -> None:
    """A real hard delete removes facts and never reuses a previously selected prompt value."""
    content = "revenue metric excludes generated refund rows"
    memory = create_memory(db, MemoryCreate(content=content))
    assert retrieve(db, "revenue metric").entries[0].id == memory.id
    deletion = delete_memory(db, memory.id)
    assert list_memories(db, include_archived=True) == []
    assert deletion.deleted_ids == [memory.id]
    assert content not in deletion.model_dump_json()
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([ModelResponse(content="No stored guidance is available.")])
    list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Explain the revenue metric"),
            provider=provider,
        )
    )
    assert len(provider.requests) == 1
    assert all(segment.name != "memory" for segment in provider.requests[0].segments)
    assert content not in provider.requests[0].model_dump_json()


def test_delete_memory_when_provenance_nested_deletes_each_archived_source_once(
    db: Database,
) -> None:
    """Nested consolidation links may repeat a source but never preserve its deleted content."""
    records = [
        entry("root").model_copy(update={"source_memory_ids": ["one", "two"]}),
        entry("one").model_copy(update={"archived": True, "source_memory_ids": ["two"]}),
        entry("two").model_copy(update={"archived": True}),
    ]
    with db.session() as session:
        for record in records:
            session.add(MemoryRow(id=record.id, payload=record.model_dump(mode="json")))
        session.commit()
    audit = delete_memory(db, "root")
    assert audit.deleted_ids == ["one", "root", "two"]
    assert list_memories(db, include_archived=True) == []
