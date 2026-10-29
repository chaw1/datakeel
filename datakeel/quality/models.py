# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed immutable domain evaluation results."""

from pydantic import Field, JsonValue

from datakeel.core.dq_views import DqSummary
from datakeel.core.media_models import MediaSummary
from datakeel.core.models import AssetRef, Record
from datakeel.quality.tabular_models import TabularAssessment


class IssueView(Record):
    """Measured quality or compliance issue."""

    dimension: str
    severity: str
    message: str
    code: str | None = None


class DimensionView(Record):
    """One weighted measured quality dimension."""

    score: float
    weight: float
    configured_weight: float | None = None
    included: bool = True
    details: dict[str, JsonValue]


class QualityConfig(Record):
    """Validated scoring rules for one dataset manifest."""

    weights: dict[str, float]
    thresholds: dict[str, float]
    exclude_annotation_when_absent: bool
    distribution_field: str
    min_size_bytes: int
    min_image_width: int
    min_image_height: int
    allowed_formats: dict[str, list[str]]


class QualityView(Record):
    """Five-dimensional quality evaluation."""

    dimensions: dict[str, DimensionView]
    total: float
    grade: str
    issues: list[IssueView]
    file_count: int
    config: QualityConfig
    tabular: TabularAssessment | None = None
    rules: DqSummary | None = Field(default=None, exclude_if=lambda value: value is None)
    media: MediaSummary | None = Field(default=None, exclude_if=lambda value: value is None)


class ChapterView(Record):
    """One evidence-grounded report section."""

    title: str
    body: str


class ReportView(Record):
    """Rule report and optional enrichment provenance."""

    chapters: list[ChapterView]
    body: str
    baseline: str
    baseline_verification: str
    fallback: bool
    source: str
    llm_body: str | None = None
    fallback_reason: str | None = None


class GovernanceRead(Record):
    """Bind a quality/report view to the exact training provenance used to compute it."""

    data: QualityView | ReportView
    asset_refs: tuple[AssetRef, ...] = ()
