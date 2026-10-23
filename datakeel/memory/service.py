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
    MemorySelection,
)
from datakeel.core.models import utcnow
from datakeel.operators.text.pii_redact import EMAIL, PHONE
from datakeel.storage import memory_store
from datakeel.storage.database import Database


def create_memory(
    db: Database,
    request: MemoryCreate,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
) -> MemoryEntry:
    """Redact both supported PII classes before any memory content is persisted."""
    content = PHONE.sub("[REDACTED]", EMAIL.sub("[REDACTED]", request.content))
    return memory_store.create(
        db, request.model_copy(update={"content": content}), clock(), policy or MemoryPolicy()
    )


def list_memories(
    db: Database,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
    include_archived: bool = False,
) -> list[MemoryEntry]:
    """List current entries; an optional dataset filter also includes global entries."""
    return memory_store.list_entries(
        db, dataset_id, clock(), policy or MemoryPolicy(), include_archived=include_archived
    )


def get_memory(
    db: Database,
    identifier: str,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
) -> MemoryEntry:
    """Read current strength and provenance for one memory identity."""
    return memory_store.get(db, identifier, clock(), policy or MemoryPolicy())


def select_memories(
    db: Database,
    query: str,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
) -> MemorySelection:
    """Retrieve a fresh bounded prompt without recording a model use yet."""
    return memory_store.select_memories(db, query, dataset_id, clock(), policy or MemoryPolicy())


def reinforce_memories(
    db: Database,
    identifiers: list[str],
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
) -> None:
    """Record actual use after a model attempt; absent identities remain absent."""
    memory_store.reinforce(db, identifiers, clock(), policy or MemoryPolicy())


def retrieve(
    db: Database,
    query: str,
    dataset_id: str | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    policy: MemoryPolicy | None = None,
) -> MemorySelection:
    """Select and reinforce with one clock sample for explicit non-model consumers."""
    now = clock()
    selected = memory_store.select_memories(db, query, dataset_id, now, policy or MemoryPolicy())
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
