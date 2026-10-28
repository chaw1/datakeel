# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-free provenance survives deletion and rejects unresolvable legacy attribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    MemorySourceSnapshot,
    MessageInput,
)
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.core.memory_models import MemoryEntry
from datakeel.core.models import AssetRef, JsonDocument, utcnow
from datakeel.storage.conversation_asset_refs import conversation_asset_refs
from datakeel.storage.conversation_memory_sources import remember_memory_sources
from datakeel.storage.conversation_store import begin, create, get, store
from datakeel.storage.data_asset_context import project_agent_history
from datakeel.storage.memory_rows import MemoryRow, MemoryUseRow

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database


def _entry(identifier: str = "legacy-memory") -> MemoryEntry:
    now = utcnow()
    return MemoryEntry(
        id=identifier,
        content="Generated legacy note",
        dataset_id="generated-dataset",
        created_at=now,
        reinforced_at=now,
    )


def _conversation(db: Database, used: JsonValue) -> Conversation:
    return store(
        db,
        Conversation(
            id="legacy-conversation",
            config=ConversationCreate(),
            messages=[ChatMessage(role="assistant", content="Generated derived marker")],
            events=[JsonDocument({"event": "done", "used_memory_ids": used})],
        ),
    )


def test_legacy_memory_cycle_resolves_dataset_once_without_looping(db: Database) -> None:
    """A retained source graph is traversed with visited identities instead of recursive calls."""
    entry = _entry().model_copy(update={"source_memory_ids": ["legacy-memory"]})
    with db.session() as session:
        session.add(MemoryRow(id=entry.id, payload=entry.model_dump(mode="json")))
        session.commit()
    conversation = _conversation(db, [entry.id])
    assert conversation_asset_refs(db, conversation.id) == (AssetRef(asset_id="generated-dataset"),)


@pytest.mark.parametrize("used", [["deleted-memory"], "invalid-list", [123]])
def test_unresolved_legacy_memory_provenance_is_projected_fail_closed(
    db: Database, used: JsonValue
) -> None:
    """Missing and malformed attribution cannot turn an old derived response into public data."""
    conversation = _conversation(db, used)
    with pytest.raises(AuthorizationError, match="apply for access"):
        conversation_asset_refs(db, conversation.id)
    projected = project_agent_history(db, conversation)
    assert projected.messages == []
    assert projected.events == []
    assert get(db, conversation.id) == conversation


def test_missing_memory_source_conversation_is_denied(db: Database) -> None:
    """A legacy provenance edge whose conversation disappeared has no safe public fallback."""
    entry = _entry().model_copy(update={"source_conversation_ids": ["unavailable-conversation"]})
    with db.session() as session:
        session.add(MemoryRow(id=entry.id, payload=entry.model_dump(mode="json")))
        session.commit()
    conversation = _conversation(db, [entry.id])
    with pytest.raises(AuthorizationError, match="source history is unavailable"):
        conversation_asset_refs(db, conversation.id)


def test_memory_snapshots_merge_resource_identities_under_the_current_lease(db: Database) -> None:
    """Attribution only grows for a consumed identity and cannot be changed by a stale writer."""
    conversation = create(db, ConversationCreate())
    lease = begin(db, conversation.id, MessageInput(content="Generated turn"))
    entry = _entry()
    remember_memory_sources(db, conversation.id, lease.token, [entry])
    remember_memory_sources(db, conversation.id, lease.token, [entry])
    remember_memory_sources(
        db,
        conversation.id,
        lease.token,
        [entry.model_copy(update={"dataset_id": "second-generated-dataset"})],
    )
    snapshots = get(db, conversation.id).memory_sources
    assert len(snapshots) == 1
    assert {ref.asset_id for ref in snapshots[0].asset_refs} == {
        "generated-dataset",
        "second-generated-dataset",
    }
    assert entry.content not in str(snapshots)
    with pytest.raises(ConflictError, match="lease was lost"):
        remember_memory_sources(db, conversation.id, "stale-token", [entry])


def test_child_snapshot_resolves_root_reinforcement_after_memory_hard_delete(db: Database) -> None:
    """A child's content-free source snapshot covers the root's durable memory-use identity."""
    root = create(db, ConversationCreate())
    child = store(
        db,
        Conversation(
            id="generated-child",
            config=ConversationCreate(),
            parent_conversation_id=root.id,
            root_conversation_id=root.id,
            memory_sources=(
                MemorySourceSnapshot(
                    memory_id="deleted-child-memory",
                    asset_refs=(AssetRef(asset_id="generated-dataset"),),
                ),
            ),
        ),
    )
    with db.session() as session:
        session.add(
            MemoryUseRow(
                root_conversation_id=root.id,
                user_message_number=1,
                memory_id="deleted-child-memory",
            )
        )
        session.commit()
    expected = (AssetRef(asset_id="generated-dataset"),)
    assert conversation_asset_refs(db, root.id) == expected
    assert conversation_asset_refs(db, child.id) == expected
