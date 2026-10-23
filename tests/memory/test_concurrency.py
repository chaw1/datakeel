# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Collection locks keep concurrent writes and hard deletion coherent on both database stacks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from datakeel.core.memory_models import MemoryCreate
from datakeel.memory.service import create_memory, delete_memory, list_memories, reinforce_memories

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_create_when_same_key_written_concurrently_returns_one_durable_identity(
    db: Database,
) -> None:
    """A first-write race cannot bypass idempotency or create duplicate memory facts."""
    request = MemoryCreate(content="revenue metric guidance", idempotency_key="concurrent")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_memory, db, request)
        second = executor.submit(create_memory, db, request)
        results = [first.result(timeout=10), second.result(timeout=10)]
    assert results[0].id == results[1].id
    assert len(list_memories(db)) == 1


def test_delete_when_reinforcement_races_never_restores_deleted_fact(db: Database) -> None:
    """Either transaction ordering ends in hard deletion without a stale row being recreated."""
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"))
    with ThreadPoolExecutor(max_workers=2) as executor:
        reinforcement = executor.submit(reinforce_memories, db, [entry.id])
        deletion = executor.submit(delete_memory, db, entry.id)
        reinforcement.result(timeout=10)
        audit = deletion.result(timeout=10)
    assert audit.deleted_ids == [entry.id]
    assert list_memories(db, include_archived=True) == []
