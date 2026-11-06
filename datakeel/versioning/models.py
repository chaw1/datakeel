# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen contracts for versioned SQLite migrations and their public reports."""

from collections.abc import Callable
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field
from sqlalchemy.engine import Connection

from datakeel.core.models import BoundaryModel


class SchemaObject(BoundaryModel):
    """Freeze a complete SQLite schema object, including constraint SQL."""

    kind: str
    name: str
    table: str
    sql: str


class BaselineDefinition(BoundaryModel):
    """Identify semantics without inferring a release from a database's contents."""

    id: str
    objects: tuple[SchemaObject, ...]
    releases: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()


class MigrationDefinition(BoundaryModel):
    """Bind ordered forward code, complete source closure and expected target semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    version: int = Field(ge=1)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str
    target: BaselineDefinition
    minimum_reader: int = Field(default=1, ge=1)
    forward: Callable[[Connection], None]
    preserve_facts: bool = True
    checksum_sources: tuple[str, ...] = ()


class DatabaseStatus(BoundaryModel):
    """Stable CLI JSON document; unavailable facts are explicitly null."""

    format_version: Literal[1] = 1
    state: Literal[
        "missing", "empty", "unversioned", "current", "pending", "ahead", "invalid", "isolated"
    ]
    baseline: str | None = None
    version: int = 0
    pending: tuple[int, ...] = ()
    release_source: Literal["unknown"] = "unknown"
    ledger_healthy: bool = False
    minimum_reader: int | None = None
    error: str | None = None
    exit_code: Literal[0, 2, 3, 4, 5, 6] = 0
    backup_manifest: str | None = None
    applied: tuple[int, ...] = ()


class LedgerRecord(BoundaryModel):
    """Validate persisted ledger metadata before treating a prefix as trustworthy."""

    version: int = Field(ge=1, strict=True)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline: str = Field(min_length=1)
    minimum_reader: int = Field(ge=1, strict=True)
    applied_at: AwareDatetime
    campaign: str = Field(min_length=1)
    facts: str = Field(pattern=r"^[0-9a-f]{64}$")
