# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen quality projections of recorded table and time-series evidence."""

from typing import Literal

from datakeel.core.models import BoundaryModel

TabularDimension = Literal["completeness", "consistency", "uniqueness", "distribution"]


class TabularFinding(BoundaryModel):
    """Retain a precise recorded reason without retaining sensitive source cell values."""

    dimension: TabularDimension
    rule: str
    file_id: str
    filename: str
    column: str
    device: str = ""
    rows: tuple[int, ...] = ()
    start_ms: int | None = None
    end_ms: int | None = None
    threshold: float | None = None
    window: int = 1
    detail: str
    recommendation: str


class ProfileColumnBrief(BoundaryModel):
    """Describe a column using aggregate profile evidence only."""

    name: str
    inferred_type: str
    null_rate: float
    unique_rate: float
    pii_kinds: tuple[str, ...] = ()


class TabularFileAssessment(BoundaryModel):
    """Expose deterministic per-file scores and report aggregates."""

    file_id: str
    filename: str
    row_count: int
    scores: dict[TabularDimension, float]
    columns: tuple[ProfileColumnBrief, ...] = ()
    findings: tuple[TabularFinding, ...] = ()
    anomaly_intervals: int = 0
    total_gap_ms: int = 0


class TabularAssessment(BoundaryModel):
    """Carry all profiled file evidence between scoring and report assembly."""

    files: tuple[TabularFileAssessment, ...] = ()
    scores: dict[TabularDimension, float]
