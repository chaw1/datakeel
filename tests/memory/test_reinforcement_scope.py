# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable user-question scopes bound reinforcement across attempts and connections."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.memory_models import MemoryCreate, MemoryPolicy, MemoryUseScope
from datakeel.memory.service import (
    create_memory,
    delete_memory,
    get_memory,
    list_memories,
    reinforce_memories,
)
from datakeel.storage.conversation_store import create
from datakeel.storage.memory_rows import MemoryRow
from tests.memory.helpers import NOW, entry

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _scope(db: Database) -> MemoryUseScope:
    conversation = create(db, ConversationCreate())
    return MemoryUseScope(root_conversation_id=conversation.id, user_message_number=1)


def test_reinforcement_when_scope_repeated_increases_strength_once(db: Database) -> None:
    """Three actual uses of one fact in a question contribute exactly one increment."""
    scope = _scope(db)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    for _ in range(3):
        reinforce_memories(db, [entry.id, entry.id], scope=scope, clock=lambda: NOW)
    result = get_memory(db, entry.id, clock=lambda: NOW)
    assert result.strength == result.current_strength == 1.5
    assert result.last_used_at == result.reinforced_at == NOW


def test_reinforcement_when_scope_reused_later_refreshes_only_last_use(db: Database) -> None:
    """A later use preserves the original reinforcement clock and its exponential decay."""
    scope = _scope(db)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: NOW)
    later = NOW + timedelta(days=14)
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: later)
    result = get_memory(db, entry.id, clock=lambda: later)
    assert result.strength == 1.5
    assert result.current_strength == 0.75
    assert result.reinforced_at == NOW
    assert result.last_used_at == later


@pytest.mark.parametrize("different_root", [False, True])
def test_reinforcement_when_question_or_root_changes_increases_again(
    db: Database, *, different_root: bool
) -> None:
    """Both a new question and another conversation receive their own reinforcement."""
    scope = _scope(db)
    next_scope = (
        _scope(db) if different_root else scope.model_copy(update={"user_message_number": 2})
    )
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: NOW)
    reinforce_memories(db, [entry.id], scope=next_scope, clock=lambda: NOW)
    assert get_memory(db, entry.id, clock=lambda: NOW).strength == 2


def test_reinforcement_when_same_scope_races_increases_once(db: Database) -> None:
    """Independent transactions cannot both claim the same question-memory use."""
    scope = _scope(db)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(reinforce_memories, db, [entry.id], scope=scope, clock=lambda: NOW)
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=10)
    assert get_memory(db, entry.id, clock=lambda: NOW).strength == 1.5


def test_reinforcement_when_database_reconnects_preserves_question_use(db: Database) -> None:
    """Closing every pooled connection does not erase a committed reinforcement identity."""
    scope = _scope(db)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: NOW)
    db.engine.dispose()
    restored_scope = MemoryUseScope.model_validate_json(scope.model_dump_json())
    reinforce_memories(db, [entry.id], scope=restored_scope, clock=lambda: NOW)
    assert get_memory(db, entry.id, clock=lambda: NOW).strength == 1.5


def test_reinforcement_when_memory_deleted_preserves_hard_deletion(db: Database) -> None:
    """Use records neither prevent deleting a fact nor recreate it on a repeated attempt."""
    scope = _scope(db)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=lambda: NOW)
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: NOW)
    delete_memory(db, entry.id, clock=lambda: NOW)
    reinforce_memories(db, [entry.id, "absent"], scope=scope, clock=lambda: NOW)
    reinforce_memories(
        db,
        [entry.id],
        scope=scope.model_copy(update={"user_message_number": 2}),
        clock=lambda: NOW,
    )
    assert list_memories(db, include_archived=True) == []


def test_reinforcement_when_memory_archived_does_not_restore_or_touch_it(db: Database) -> None:
    """A consolidated source stays archived and unused even under a new question scope."""
    scope = _scope(db)
    policy = MemoryPolicy(max_entries=1)
    entry = create_memory(
        db, MemoryCreate(content="revenue metric guidance"), policy=policy, clock=lambda: NOW
    )
    reinforce_memories(db, [entry.id], scope=scope, clock=lambda: NOW)
    merged = create_memory(
        db, MemoryCreate(content="Revenue metric guidance"), policy=policy, clock=lambda: NOW
    )
    archived_id = merged.source_memory_ids[0]
    before = get_memory(db, archived_id, clock=lambda: NOW)
    reinforce_memories(db, [archived_id], scope=scope, clock=lambda: NOW)
    assert get_memory(db, archived_id, clock=lambda: NOW) == before
    assert before.archived
    assert before.last_used_at is None


def test_reinforcement_when_old_memory_table_migrated_preserves_facts_and_adds_scope(
    unmigrated_db: Database,
) -> None:
    """An existing fact survives additive migration and gains durable question deduplication."""
    db = unmigrated_db
    with db.engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE memories (id VARCHAR PRIMARY KEY, payload JSON NOT NULL)")
        )
    original = entry("generated-memory")
    with db.session() as session:
        session.add(MemoryRow(id=original.id, payload=original.model_dump(mode="json")))
        session.commit()
    db.migrate()
    db.migrate()
    scope = _scope(db)
    assert get_memory(db, original.id, clock=lambda: NOW) == original
    for _ in range(2):
        reinforce_memories(db, [original.id], scope=scope, clock=lambda: NOW)
    assert get_memory(db, original.id, clock=lambda: NOW).strength == 1.5
