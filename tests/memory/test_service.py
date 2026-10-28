# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Memory writes, scope isolation, lazy strength and deletion use isolated fact stores."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.memory_models import MemoryCreate, MemoryPolicy
from datakeel.memory.service import (
    create_memory,
    delete_memory,
    get_memory,
    list_deletions,
    list_memories,
    reinforce_memories,
    retrieve,
    select_memories,
)
from datakeel.storage.conversation_store import create
from datakeel.storage.dataset_service import DatasetInput, create_dataset
from tests.memory.helpers import NOW

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_memory_when_store_empty_returns_no_segment(db: Database) -> None:
    """An empty memory store contributes no model context or historical content."""
    assert list_memories(db) == []
    assert retrieve(db, "revenue metric").text == ""
    assert select_memories(db, "revenue metric").entries == []
    assert list_deletions(db) == []


def test_create_when_pii_present_redacts_before_storage_and_preserves_dates(db: Database) -> None:
    """Explicit writing reuses the corrected shared patterns without storing original PII."""
    content = "Contact user@example.org or +1 (415) 555-0123; date 2026-10-24 / 2026/10/24 10:30:00"
    result = create_memory(db, MemoryCreate(content=content), clock=lambda: NOW)
    assert result.content == ("Contact [EMAIL] or [PHONE]; date 2026-10-24 / 2026/10/24 10:30:00")
    assert get_memory(db, result.id, clock=lambda: NOW) == result


def test_create_when_replayed_returns_same_entry_and_rejects_changed_or_deleted_write(
    db: Database,
) -> None:
    """Durable replay identities prevent duplicate writes and post-deletion resurrection."""
    request = MemoryCreate(content="revenue metric definition", idempotency_key="replay")
    first = create_memory(db, request, clock=lambda: NOW)
    assert create_memory(db, request, clock=lambda: NOW) == first
    with pytest.raises(ConflictError, match="different write"):
        create_memory(db, request.model_copy(update={"content": "changed metric"}))
    delete_memory(db, first.id)
    with pytest.raises(ConflictError, match="was deleted"):
        create_memory(db, request)
    assert list_memories(db) == []


@pytest.mark.parametrize(
    "body",
    [
        MemoryCreate(content="revenue metric", dataset_id="missing"),
        MemoryCreate(content="revenue metric", source_conversation_id="missing"),
    ],
)
def test_create_when_scope_or_source_missing_rejects_without_persistence(
    db: Database, body: MemoryCreate
) -> None:
    """Unresolved provenance cannot enter the authoritative memory store."""
    with pytest.raises(NotFoundError):
        create_memory(db, body)
    assert list_memories(db) == []


def test_select_when_dataset_set_combines_only_global_and_matching_scope(db: Database) -> None:
    """Listing may span scopes, but a conversation without a dataset gets global memory only."""
    first = create_dataset(db, DatasetInput(name="first"))
    second = create_dataset(db, DatasetInput(name="second"))
    conversation = create(db, ConversationCreate(dataset_id=first.id))
    entries = [
        create_memory(
            db,
            MemoryCreate(
                content="revenue metric definition",
                dataset_id=dataset_id,
                source_conversation_id=conversation.id,
            ),
        )
        for dataset_id in (None, first.id, second.id)
    ]
    assert len(list_memories(db)) == 3
    assert {item.id for item in list_memories(db, first.id)} == {entries[0].id, entries[1].id}
    assert {item.id for item in retrieve(db, "revenue metric", first.id).entries} == {
        entries[0].id,
        entries[1].id,
    }
    assert [item.id for item in select_memories(db, "revenue metric").entries] == [entries[0].id]
    assert entries[0].source_conversation_ids == [conversation.id]


def test_select_then_reinforce_when_clock_fixed_updates_only_actual_selected_entries(
    db: Database,
) -> None:
    """Read-only selection leaves strength untouched and repeated IDs count as one use."""
    entry = create_memory(db, MemoryCreate(content="revenue metric"), clock=lambda: NOW)
    later = NOW + timedelta(days=14)
    assert (
        select_memories(db, "revenue metric", clock=lambda: later).entries[0].current_strength
        == 0.5
    )
    assert get_memory(db, entry.id, clock=lambda: later).last_used_at is None
    reinforce_memories(db, [entry.id, entry.id, "absent"], clock=lambda: later)
    updated = get_memory(db, entry.id, clock=lambda: later)
    assert updated.strength == 1
    assert updated.last_used_at == updated.reinforced_at == later
    retrieve(db, "revenue metric", clock=lambda: later)
    assert get_memory(db, entry.id, clock=lambda: later).strength == 1.5


def test_create_when_limit_exceeded_retains_sources_and_cascades_hard_delete(db: Database) -> None:
    """A consolidated representative preserves source links and deletes all archived content."""
    policy = MemoryPolicy(max_entries=1)
    source = create(db, ConversationCreate())
    first = create_memory(
        db,
        MemoryCreate(content="Revenue metric", source_conversation_id=source.id),
        policy=policy,
        clock=lambda: NOW,
    )
    reinforce_memories(db, [first.id], clock=lambda: NOW)
    request = MemoryCreate(content="revenue   metric", idempotency_key="merged")
    second = create_memory(db, request, policy=policy, clock=lambda: NOW)
    assert second.id == first.id
    assert len(second.source_memory_ids) == 1
    assert create_memory(db, request, policy=policy, clock=lambda: NOW).id == first.id
    archived_id = second.source_memory_ids[0]
    reinforce_memories(db, [archived_id], clock=lambda: NOW)
    assert get_memory(db, archived_id, clock=lambda: NOW).last_used_at is None
    assert len(list_memories(db, include_archived=True)) == 2
    deletion = delete_memory(db, first.id, clock=lambda: NOW)
    assert deletion.deleted_ids == sorted([first.id, archived_id])
    assert list_memories(db, include_archived=True) == []
    assert list_deletions(db) == [deletion]
    assert "revenue" not in deletion.model_dump_json().lower()
    reinforce_memories(db, [first.id], clock=lambda: NOW)
    assert select_memories(db, "revenue metric").entries == []
    with pytest.raises(NotFoundError):
        delete_memory(db, first.id)
