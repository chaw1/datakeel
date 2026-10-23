# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed contracts for deterministic fictional enterprise fixtures."""

from datetime import UTC, datetime
from pathlib import Path

from datakeel.core.models import BoundaryModel

type Cell = str | int | float | None


class TableData(BoundaryModel):
    """Describe one synthetic SQLite table and its ordered data."""

    name: str
    definition: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]


class ViewData(BoundaryModel):
    """Provide a deterministic view definition for lineage extraction."""

    name: str
    query: str


class SourceData(BoundaryModel):
    """Hold one fully synthetic source before file materialization."""

    id: str
    name: str
    tables: tuple[TableData, ...]
    views: tuple[ViewData, ...]


class SourceSample(BoundaryModel):
    """Identify one generated database and its reproducible counts."""

    id: str
    name: str
    path: Path
    row_count: int
    table_count: int
    view_count: int


class EnterpriseGold(BoundaryModel):
    """Store answers computed directly from generated rows, independently of SQL."""

    company: str = "Fictional Kitchen Co."
    reference_instant: datetime = datetime(2026, 10, 1, tzinfo=UTC)
    answers: dict[str, float]


class EnterpriseSample(BoundaryModel):
    """Return the complete local sample without exposing untyped file metadata."""

    sources: tuple[SourceSample, ...]
    gold_path: Path
    reference_instant: datetime = datetime(2026, 10, 1, tzinfo=UTC)

    @property
    def row_count(self) -> int:
        """Count generated table rows across all four sources."""
        return sum(source.row_count for source in self.sources)
