# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Memory edits preserve provenance and obey privacy, retention and access boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.memory_models import MemoryCreate, MemoryPolicy, MemoryUpdate
from datakeel.core.models import AssetRef, JsonDocument, new_id
from datakeel.dataset_store.dataset_service import import_paths
from datakeel.memory.service import (
    create_memory,
    delete_memory,
    get_memory,
    list_memories,
    reinforce_memories,
    update_memory,
)
from datakeel.storage.conversation_store import create
from tests.assets.entry_helpers import grant, publish
from tests.memory.helpers import NOW

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from datakeel.core.memory_models import MemoryDeletion, MemoryEntry
    from datakeel.storage.database import Database


def _manage(db: Database, values: Mapping[str, object]) -> None:
    plan = prepare_action(
        db, "manage_users", JsonDocument.model_validate({"request_id": new_id(), **values})
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_edit_redacts_persisted_content_without_reinforcement_or_provenance_changes(
    db: Database,
) -> None:
    """Editing a consolidated memory keeps every identity, source and decayed strength."""
    source = create(db, ConversationCreate())
    policy = MemoryPolicy(max_entries=1)
    original = create_memory(
        db,
        MemoryCreate(content="Revenue metric", source_conversation_id=source.id),
        clock=lambda: NOW,
        policy=policy,
    )
    reinforce_memories(db, [original.id], clock=lambda: NOW)
    merged = create_memory(
        db, MemoryCreate(content="revenue metric"), clock=lambda: NOW, policy=policy
    )
    assert merged.source_memory_ids
    later = NOW + timedelta(days=14)
    before = get_memory(db, merged.id, clock=lambda: later)
    edited = update_memory(
        db,
        merged.id,
        MemoryUpdate(content="  Contact user@example.org or +1 (415) 555-0123 for v2  "),
        clock=lambda: later,
    )
    assert edited.content == "Contact [REDACTED] or [REDACTED] for v2"
    assert edited.model_dump(exclude={"content"}) == before.model_dump(exclude={"content"})
    assert get_memory(db, merged.id, clock=lambda: later) == edited
    assert edited.current_strength == 0.75
    assert list_memories(db, query="v2", clock=lambda: later) == [edited]
    assert list_memories(db, query="revenue", clock=lambda: later) == []


@pytest.mark.parametrize("state", ["missing", "archived", "deleted"])
def test_edit_missing_archived_or_deleted_memory_cannot_restore_content(
    db: Database, state: str
) -> None:
    """An edit cannot recreate a removed record or reactivate a retained source."""
    original = create_memory(db, MemoryCreate(content="revenue metric"), clock=lambda: NOW)
    identifier = original.id
    if state == "archived":
        reinforce_memories(db, [identifier], clock=lambda: NOW)
        merged = create_memory(
            db,
            MemoryCreate(content="revenue metric"),
            clock=lambda: NOW,
            policy=MemoryPolicy(max_entries=1),
        )
        identifier = merged.source_memory_ids[0]
    elif state == "deleted":
        delete_memory(db, identifier)
    else:
        identifier = "missing"
    before = list_memories(db, include_archived=True, clock=lambda: NOW)
    with pytest.raises(NotFoundError, match="Memory not found"):
        update_memory(db, identifier, MemoryUpdate(content="replacement"), clock=lambda: NOW)
    assert list_memories(db, include_archived=True, clock=lambda: NOW) == before


def test_edit_requires_write_scope_for_named_actors(db: Database) -> None:
    """Read-only and unknown users cannot edit a visible memory through the service."""
    memory = create_memory(db, MemoryCreate(content="original"), clock=lambda: NOW)
    _manage(db, {"operation": "create", "user_id": "local"})
    _manage(db, {"operation": "create", "user_id": "observer", "role_ids": ["acceptance"]})
    for actor in ("unknown", "observer"):
        with pytest.raises(AuthorizationError, match="server-authorized action scope"):
            update_memory(db, memory.id, MemoryUpdate(content="replacement"), actor=actor)
    assert get_memory(db, memory.id, clock=lambda: NOW) == memory


def test_edit_requires_current_source_visibility_even_with_write_scope(
    db: Database, tmp_path: Path
) -> None:
    """The zero-user write capability does not lend the owner's protected dataset grant."""
    document = tmp_path / "generated.txt"
    document.write_text("Generated edit authorization fixture.")
    dataset = import_paths(db, "Protected memory", [document])
    asset = publish(db, AssetRef(asset_id=dataset.id))
    assert grant(db, asset, "valid", "query", subject="local")
    memory = create_memory(
        db, MemoryCreate(content="protected v2", dataset_id=dataset.id), clock=lambda: NOW
    )
    with pytest.raises(AuthorizationError, match="query grant"):
        update_memory(db, memory.id, MemoryUpdate(content="replacement"), actor="outsider")
    assert list_memories(db, query="v2", actor="outsider") == []
    assert get_memory(db, memory.id, clock=lambda: NOW) == memory
    edited = update_memory(db, memory.id, MemoryUpdate(content="protected v3"), clock=lambda: NOW)
    assert edited == memory.model_copy(update={"content": "protected v3"})


def test_edit_racing_hard_deletion_never_restores_the_memory(db: Database) -> None:
    """Both transaction orderings end in deletion, never a stale-content resurrection."""
    memory = create_memory(db, MemoryCreate(content="original memory"))
    ready = Barrier(2)

    def _edit() -> MemoryEntry:
        ready.wait(timeout=10)
        return update_memory(db, memory.id, MemoryUpdate(content="replacement"))

    def _delete() -> MemoryDeletion:
        ready.wait(timeout=10)
        return delete_memory(db, memory.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        editing = executor.submit(_edit)
        deleting = executor.submit(_delete)
        if editing.exception(timeout=10) is None:
            assert editing.result().content == "replacement"
        else:
            with pytest.raises(NotFoundError, match="Memory not found"):
                editing.result()
        audit = deleting.result(timeout=10)
    assert audit.deleted_ids == [memory.id]
    assert list_memories(db, include_archived=True) == []
    with pytest.raises(NotFoundError):
        get_memory(db, memory.id)
