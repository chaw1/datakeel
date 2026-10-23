# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Response ownership stays exclusive while abandoned process leases can be reclaimed."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ResumeInput
from datakeel.core.errors import ConflictError
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.conversation_resume import begin_resume

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_response_when_lock_live_cannot_steal_active_lease(db: Database) -> None:
    """Reject a concurrent response before it can append a message or revoke its owner."""
    conversation = create_conversation(db, ConversationCreate())
    stream = send_message(
        db,
        conversation.id,
        MessageInput(content="first"),
        provider=FakeProvider([ModelResponse(content="answer")]),
    )
    assert next(stream).event == "text"
    before = get_conversation(db, conversation.id)
    with pytest.raises(ConflictError, match="active response"):
        list(send_message(db, conversation.id, MessageInput(content="overlap")))
    assert get_conversation(db, conversation.id) == before
    assert list(stream)[-1].event == "done"


def test_response_when_process_lease_abandoned_closes_and_reclaims_under_lock(db: Database) -> None:
    """A stale token alone cannot block a fresh process that holds the execution mutex."""
    conversation = create_conversation(db, ConversationCreate())
    old = memory.begin(db, conversation.id, MessageInput(content="abandoned"))
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="continue"), provider=FakeProvider([])
        )
    )
    assert events[-1].event == "done"
    loaded = get_conversation(db, conversation.id)
    assert any(event.stop_reason == "interrupted" for event in loaded.events)
    with pytest.raises(ConflictError, match="ownership changed"):
        memory.finish(db, conversation.id, old.token, completed=True)


def test_resume_when_lease_active_rejects_overlapping_storage_request(db: Database) -> None:
    """Independent resume keys still share one conversation writer lease."""
    conversation = create_conversation(db, ConversationCreate())
    with response_lock(db, conversation.id):
        first = begin_resume(
            db, conversation.id, ResumeInput(plan_id="plan", idempotency_key="one")
        )
        with pytest.raises(ConflictError, match="active response"):
            begin_resume(db, conversation.id, ResumeInput(plan_id="plan", idempotency_key="two"))
        memory.finish(db, conversation.id, first.token, completed=False)
        second = begin_resume(
            db, conversation.id, ResumeInput(plan_id="plan", idempotency_key="one")
        )
        assert second.token != first.token
        assert memory.get(db, conversation.id).messages == []
        memory.finish(db, conversation.id, second.token, completed=True)
