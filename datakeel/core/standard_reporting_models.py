# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured field quality and bounded read-only standard queries."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel

type StandardsGrade = Literal["unmeasured", "excellent", "good", "fair", "poor"]


class StandardDimension(BoundaryModel):
    """Score the fraction of evaluated column rules that passed in one dimension."""

    score: float | None
    checked_rules: int
    failed_rules: int
    violation_count: int
    weight: float


class StandardQualityIssue(BoundaryModel):
    """Locate a measured standards issue without copying source values."""

    dimension: str
    column_id: str
    rule: str
    count: int
    message: str


class StandardsQuality(BoundaryModel):
    """Keep column quality distinct from the existing file-manifest quality contract."""

    dimensions: dict[str, StandardDimension]
    total: float | None
    grade: StandardsGrade
    column_count: int
    mapped_columns: int
    fully_checked_columns: int
    skipped_rules: int
    issues: tuple[StandardQualityIssue, ...]


class StandardCoverageParams(BoundaryModel):
    """Bound a read-only coverage query by an optional catalog table identity."""

    table_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class StandardUsageParams(BoundaryModel):
    """Find confirmed usage by exact code or a bilingual standard name."""

    standard: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=100, ge=1, le=1000)
