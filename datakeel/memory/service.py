# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit memory operations with shared redaction and an injectable business clock."""

from collections.abc import Callable
from datetime import datetime
from typing import TypedDict, Unpack

from datakeel.core.memory_models import (
    MemoryCreate,
    MemoryDeletion,
    MemoryEntry,
    MemoryPolicy,
    MemoryReadOptions,
    MemorySelection,
    MemoryUpdate,
    MemoryUseScope,
)
from datakeel.core.models import utcnow
from datakeel.core.pii import redact_pii
from datakeel.memory.retrieval import search_entries
from datakeel.storage import memory_store
from datakeel.storage.database import Database


class _MemoryReadKeywords(TypedDict, total=False):
    actor: str
    include_archived: bool


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
    query: str | None = None,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    **options: Unpack[_MemoryReadKeywords],
) -> list[MemoryEntry]:
    """List scoped entries, retaining actor and include_archived keyword compatibility."""
    read_options = MemoryReadOptions(
        actor=options.get("actor", "local"),
        include_archived=options.get("include_archived", False),
        record=True,
    )
    entries = memory_store.list_entries(
        db,
        dataset_id,
        clock(),
        policy or MemoryPolicy(),
        options=read_options,
    )
    return search_entries(entries, query) if query else entries


def update_memory(
    db: Database,
    identifier: str,
    request: MemoryUpdate,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    actor: str = "local",
) -> MemoryEntry:
    """Redact replacement content while preserving memory scope, strength and provenance."""
    content = redact_pii(request.content, replacement="[REDACTED]")
    return memory_store.update(
        db, identifier, content, clock(), policy or MemoryPolicy(), actor=actor
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
