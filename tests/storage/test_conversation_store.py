# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable memory isolates concurrent turns and replays idempotent messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.agent_models import ChatMessage, ConversationCreate, MessageInput
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, new_id
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_rows import ConversationRequestRow, ConversationRow

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_conversation_when_reloaded_keeps_every_message_and_replays_completed_request(
    db: Database,
) -> None:
    """Preserve full transcripts and replay events without appending duplicate user messages."""
    conversation = memory.create(db, ConversationCreate(dataset_id="dataset"))
    request = MessageInput(content="Find quality issues", idempotency_key="first-message")
    lease = memory.begin(db, conversation.id, request)
    for index in range(35):
        memory.append(
            db,
            conversation.id,
            lease.token,
            message=ChatMessage(role="assistant", content=f"Observation {index}"),
            model_call=True,
        )
    event = JsonDocument({"event": "done"})
    memory.append(db, conversation.id, lease.token, event=event)
    memory.finish(db, conversation.id, lease.token, completed=True)
    assert memory.begin(db, conversation.id, request).replay == [event]
    loaded = memory.get(db, conversation.id)
    assert len(loaded.messages) == 36
    assert loaded.turns == 35
    assert memory.list_all(db) == [loaded]


def test_message_when_key_reused_for_new_content_rejects_conflicting_request(db: Database) -> None:
    """Bind idempotency to content independently of an earlier successful response."""
    conversation = memory.create(db, ConversationCreate())
    first = MessageInput(content="First", idempotency_key="same-key")
    lease = memory.begin(db, conversation.id, first)
    memory.finish(db, conversation.id, lease.token, completed=True)
    with pytest.raises(ConflictError, match="different user message"):
        memory.begin(db, conversation.id, first.model_copy(update={"content": "Changed"}))


def test_conversation_when_busy_rejects_overlapping_and_duplicate_requests(db: Database) -> None:
    """Allow only one writer and keep interrupted requests from executing twice."""
    conversation = memory.create(db, ConversationCreate())
    request = MessageInput(content="First")
    lease = memory.begin(db, conversation.id, request)
    with pytest.raises(ConflictError, match="already in progress"):
        memory.begin(db, conversation.id, request)
    with pytest.raises(ConflictError, match="active response"):
        memory.begin(db, conversation.id, MessageInput(content="Concurrent"))
    memory.finish(db, conversation.id, lease.token, completed=False)
    with pytest.raises(ConflictError, match="interrupted"):
        memory.begin(db, conversation.id, request)
    assert memory.begin(db, conversation.id, MessageInput(content="Recovery")).replay is None


def test_conversation_when_old_lease_expires_new_writer_revokes_previous_owner(
    db: Database,
) -> None:
    """Recover abandoned sessions without allowing stale workers to append messages."""
    conversation = memory.create(db, ConversationCreate())
    previous = memory.begin(db, conversation.id, MessageInput(content="Old"))
    with db.session() as session:
        row = session.get(ConversationRow, conversation.id)
        assert row is not None
        row.active_until = 0
        session.commit()
    memory.begin(db, conversation.id, MessageInput(content="New"))
    with pytest.raises(ConflictError, match="ownership changed"):
        memory.append(db, conversation.id, previous.token, message=ChatMessage(role="assistant"))


def test_conversation_when_missing_rejects_reads_and_unknown_writers(db: Database) -> None:
    """Raise domain errors instead of creating phantom sessions."""
    with pytest.raises(NotFoundError, match="Conversation not found"):
        memory.get(db, new_id())
    conversation = memory.create(db, ConversationCreate())
    with pytest.raises(ConflictError, match="ownership changed"):
        memory.finish(db, conversation.id, new_id(), completed=False)


def test_request_when_storage_record_disappears_refuses_event_but_releases_owner(
    db: Database,
) -> None:
    """Keep transcript and request-event writes atomic under inconsistent request storage."""
    conversation = memory.create(db, ConversationCreate())
    request = MessageInput(content="First")
    lease = memory.begin(db, conversation.id, request)
    with db.session() as session:
        row = session.get(ConversationRequestRow, (conversation.id, request.idempotency_key))
        assert row is not None
        session.delete(row)
        session.commit()
    with pytest.raises(ConflictError, match="request disappeared"):
        memory.append(db, conversation.id, lease.token, event=JsonDocument({"event": "done"}))
    assert memory.get(db, conversation.id).events == []
    memory.finish(db, conversation.id, lease.token, completed=False)
