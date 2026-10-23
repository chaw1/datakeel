# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated read models for HTTP and application service boundaries."""

from pathlib import Path

from pydantic import ConfigDict, Field, JsonValue

from datakeel.core.models import BoundaryModel
from datakeel.governance.models import ComplianceView


class View(BoundaryModel):
    """Immutable service result with no undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FileView(View):
    """Public file evidence without a private materialized path."""

    id: str
    filename: str
    sha256: str
    size: int
    modality: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DatasetView(View):
    """Dataset summary containing its current governance configuration."""

    id: str
    name: str
    file_count: int
    created_at: float
    metadata: dict[str, JsonValue]
    quality_config: dict[str, JsonValue]
    template: dict[str, JsonValue] | None
    compliance: dict[str, JsonValue]


class DatasetQualityView(DatasetView):
    """Extend an explicitly requested dataset summary with its latest measured score."""

    quality_score: float | None


class VersionView(View):
    """Immutable manifest snapshot."""

    id: str
    created_at: float
    file_count: int
    manifest: list[FileView]


class DownloadView(View):
    """Resolved local object and user-visible filename."""

    path: Path
    filename: str


class TemplateView(View):
    """Saved standard template and resulting compliance."""

    template: dict[str, JsonValue] | None
    compliance: ComplianceView


class MetadataView(View):
    """Current metadata and the standard governing future edits."""

    values: dict[str, JsonValue]
    template: dict[str, JsonValue] | None


class MetadataSavedView(View):
    """Updated metadata and its measured compliance."""

    values: dict[str, JsonValue]
    compliance: ComplianceView


class MetadataChangeView(View):
    """A field-level audited metadata transition."""

    field: str
    before: JsonValue
    after: JsonValue
    source: str
    reason: str
    occurred_at: float
