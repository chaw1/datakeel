# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only standards revisions and read-only assessment boundaries."""

from datetime import datetime

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.standard_models import (
    ColumnCheck,
    ColumnMapping,
    ColumnProfile,
    StandardsContract,
    StandardsCoverage,
)


class StandardsState(BoundaryModel):
    """Freeze the complete effective contract and human-confirmed mappings."""

    revision: int = Field(default=0, ge=0)
    contract: StandardsContract = Field(default_factory=StandardsContract)
    mappings: tuple[ColumnMapping, ...] = ()


class StandardsRevision(StandardsState):
    """Attribute one immutable state transition to its controlled action."""

    plan_id: str
    actor: str
    action_type: str
    event_id: str
    created_at: datetime


class StandardsHistory(BoundaryModel):
    """Expose every committed standards revision in ascending order."""

    revisions: tuple[StandardsRevision, ...]


class StandardsReport(BoundaryModel):
    """Combine metadata, confirmed associations, checks and coverage without raw values."""

    profiles: tuple[ColumnProfile, ...]
    mappings: tuple[ColumnMapping, ...]
    checks: tuple[ColumnCheck, ...]
    coverage: StandardsCoverage
