# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen boundaries for explicit, scoped cross-conversation memories."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from datakeel.core.models import BoundaryModel, new_id


class MemoryPolicy(BoundaryModel):
    """Bound deterministic retention while keeping retrieval constants fixed."""

    half_life_days: float = Field(default=14, gt=0)
    max_entries: int = Field(default=200, ge=1)


class MemoryWrite(BoundaryModel):
    """Accept only explicit memory content and its intended scope."""

    content: str = Field(min_length=1, max_length=6000)
    dataset_id: str | None = Field(default=None, min_length=1)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Reject whitespace-only entries before they reach persistence."""
        value = value.strip()
        if not value:
            msg = "Memory content must not be blank"
            raise ValueError(msg)
        return value


class MemoryCreate(MemoryWrite):
    """Bind an explicit write to its optional source and replay key."""

    source_conversation_id: str | None = Field(default=None, min_length=1)
    idempotency_key: str = Field(default_factory=new_id, min_length=1, max_length=200)


class MemoryEntry(BoundaryModel):
    """Expose current strength and provenance without leaking persistence rows."""

    id: str
    content: str
    dataset_id: str | None = None
    source_conversation_ids: list[str] = Field(default_factory=list[str])
    source_memory_ids: list[str] = Field(default_factory=list[str])
    created_at: datetime
    strength: float = Field(default=1.0, ge=0.05, le=3)
    reinforced_at: datetime
    current_strength: float = Field(default=1.0, ge=0.05, le=3)
    last_used_at: datetime | None = None
    archived: bool = False


class MemorySelection(BoundaryModel):
    """Carry the selected entries and their complete bounded data-only prompt."""

    entries: list[MemoryEntry] = Field(default_factory=list[MemoryEntry])
    text: str = ""


class MemoryUseScope(BoundaryModel):
    """Identify one root user question shared by model attempts and delegated descendants."""

    root_conversation_id: str = Field(min_length=1)
    user_message_number: int = Field(ge=1)


class MemoryDeletion(BoundaryModel):
    """Retain deletion evidence containing identities only, never memory content."""

    id: str
    memory_id: str
    deleted_ids: list[str]
    kind: Literal["MEMORY_DELETED"] = "MEMORY_DELETED"
    created_at: datetime
