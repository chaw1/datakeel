# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed immutable domain evaluation results."""

from pydantic import JsonValue

from datakeel.core.models import Record


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
