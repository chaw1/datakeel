# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit memory creation, scoped management and content-free deletion audit."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.memory_models import MemoryCreate, MemoryDeletion, MemoryEntry
from datakeel.memory import service

router = APIRouter(prefix="/api/agent/memories", tags=["memory"])


@router.get("")
def list_all(
    db: DatabaseDependency, request: Request, dataset_id: str | None = None
) -> list[MemoryEntry]:
    """List active memories, optionally restricted to global and one dataset scope."""
    return service.list_memories(db, dataset_id, actor=http_actor(request))


@router.post("")
def create(body: MemoryCreate, db: DatabaseDependency, request: Request) -> MemoryEntry:
    """Redact PII and persist an explicitly supplied memory exactly once."""
    return service.create_memory(db, body, actor=http_actor(request))


@router.get("/audit")
def audit(db: DatabaseDependency) -> list[MemoryDeletion]:
    """Read hard-deletion evidence that contains no memory content."""
    return service.list_deletions(db)


@router.get("/{memory_id}")
def get(memory_id: str, db: DatabaseDependency, request: Request) -> MemoryEntry:
    """Read one memory and its current decayed strength."""
    return service.get_memory(db, memory_id, actor=http_actor(request))


@router.delete("/{memory_id}")
def delete(memory_id: str, db: DatabaseDependency) -> MemoryDeletion:
    """Hard-delete the memory and archived provenance records in one transaction."""
    return service.delete_memory(db, memory_id)
