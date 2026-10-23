# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit memory creation, scoped management and content-free deletion audit."""

from fastapi import APIRouter

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.memory_models import MemoryCreate, MemoryDeletion, MemoryEntry
from datakeel.memory import service

router = APIRouter(prefix="/api/agent/memories", tags=["memory"])


@router.get("")
def list_all(db: DatabaseDependency, dataset_id: str | None = None) -> list[MemoryEntry]:
    """List active memories, optionally restricted to global and one dataset scope."""
    return service.list_memories(db, dataset_id)


@router.post("")
def create(body: MemoryCreate, db: DatabaseDependency) -> MemoryEntry:
    """Redact PII and persist an explicitly supplied memory exactly once."""
    return service.create_memory(db, body)


@router.get("/audit")
def audit(db: DatabaseDependency) -> list[MemoryDeletion]:
    """Read hard-deletion evidence that contains no memory content."""
    return service.list_deletions(db)


@router.get("/{memory_id}")
def get(memory_id: str, db: DatabaseDependency) -> MemoryEntry:
    """Read one memory and its current decayed strength."""
    return service.get_memory(db, memory_id)


@router.delete("/{memory_id}")
def delete(memory_id: str, db: DatabaseDependency) -> MemoryDeletion:
    """Hard-delete the memory and archived provenance records in one transaction."""
    return service.delete_memory(db, memory_id)
