# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit memory operations with shared redaction and an injectable business clock."""

from collections.abc import Callable
from datetime import datetime

from datakeel.core.memory_models import (
    MemoryCreate,
    MemoryDeletion,
    MemoryEntry,
    MemoryPolicy,
    MemoryReadOptions,
    MemorySelection,
    MemoryUseScope,
)
from datakeel.core.models import utcnow
from datakeel.core.pii import redact_pii
from datakeel.storage import memory_store
from datakeel.storage.database import Database


def create_memory(
    db: Database,
    request: MemoryCreate,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    actor: str = "local",
) -> MemoryEntry:
    """Redact shared privacy classes before any memory content is persisted."""
    content = redact_pii(request.content, replacement="[REDACTED]")
    return memory_store.create(
        db,
        request.model_copy(update={"content": content}),
        clock(),
        policy or MemoryPolicy(),
        actor=actor,
    )


def list_memories(
    db: Database,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    include_archived: bool = False,
    actor: str = "local",
) -> list[MemoryEntry]:
    """List current entries; an optional dataset filter also includes global entries."""
    return memory_store.list_entries(
        db,
        dataset_id,
        clock(),
        policy or MemoryPolicy(),
        options=MemoryReadOptions(actor=actor, include_archived=include_archived, record=True),
    )


def get_memory(
    db: Database,
    identifier: str,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    actor: str = "local",
) -> MemoryEntry:
    """Read current strength and provenance for one memory identity."""
    return memory_store.get(db, identifier, clock(), policy or MemoryPolicy(), actor=actor)


def select_memories(
    db: Database,
    query: str,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    actor: str = "local",
) -> MemorySelection:
    """Retrieve a fresh bounded prompt without recording a model use yet."""
    return memory_store.select_memories(
        db, query, dataset_id, clock(), policy or MemoryPolicy(), actor=actor
    )


def reinforce_memories(
    db: Database,
    identifiers: list[str],
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    scope: MemoryUseScope | None = None,
) -> None:
    """Record actual use, strengthening once per scoped question without restoring deletions."""
    memory_store.reinforce(db, identifiers, clock(), policy or MemoryPolicy(), scope)


def retrieve(
    db: Database,
    query: str,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    actor: str = "local",
) -> MemorySelection:
    """Select and reinforce with one clock sample for explicit non-model consumers."""
    now = clock()
    selected = memory_store.select_memories(
        db, query, dataset_id, now, policy or MemoryPolicy(), actor=actor
    )
    memory_store.reinforce(
        db, [item.id for item in selected.entries], now, policy or MemoryPolicy()
    )
    return selected


def delete_memory(
    db: Database, identifier: str, *, clock: Callable[[], datetime] = utcnow
) -> MemoryDeletion:
    """Hard-delete content and archived sources while retaining only audit identities."""
    return memory_store.delete(db, identifier, clock())


def list_deletions(db: Database) -> list[MemoryDeletion]:
    """List content-free evidence of explicit memory deletion."""
    return memory_store.list_audit(db)
