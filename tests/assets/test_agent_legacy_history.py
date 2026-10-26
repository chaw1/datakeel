# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable reinforcement records protect interrupted history written before provenance snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.agent_models import ChatMessage, Conversation, ConversationCreate
from datakeel.core.models import JsonDocument
from datakeel.memory.service import delete_memory
from datakeel.storage.conversation_store import get, store
from datakeel.storage.memory_rows import MemoryUseRow
from tests.assets.test_agent_history_reads import (
    MARKER,
    assert_fresh_context,
    history_fixture,
    invalidate,
    usage_count,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("state", ["revoked", "expired", "deleted"])
def test_legacy_interrupted_memory_consumerusage_count_durable_reinforcement_provenance(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """An empty terminal memory list cannot erase the existing source identities of a turn."""
    client, _, _, grant_id, memories = history_fixture(db, tmp_path)
    conversation = store(
        db,
        Conversation(
            id="legacy-interrupted-consumer",
            config=ConversationCreate(),
            messages=[
                ChatMessage(role="user", content="Legacy generated memory review"),
                ChatMessage(role="assistant", content=f"Derived interrupted filename {MARKER}"),
            ],
            events=[
                JsonDocument({"event": "text", "text": MARKER}),
                JsonDocument({"event": "stopped", "stop_reason": "interrupted"}),
                JsonDocument({"event": "done", "used_memory_ids": []}),
            ],
        ),
    )
    with db.session() as session:
        session.add(
            MemoryUseRow(
                root_conversation_id=conversation.id,
                user_message_number=1,
                memory_id=memories[0],
            )
        )
        session.commit()
    endpoint = f"/api/agent/conversations/{conversation.id}"
    assert MARKER in client.get(endpoint).text
    if state == "deleted":
        delete_memory(db, memories[0])
    else:
        invalidate(db, grant_id, state, monkeypatch)
    before = usage_count(db)
    response = client.get(endpoint)
    assert response.status_code == 200
    assert MARKER not in response.text
    assert "Legacy generated memory review" in response.text
    assert usage_count(db) == before
    assert get(db, conversation.id) == conversation
    if state != "deleted":
        assert_fresh_context(client, conversation.id)
