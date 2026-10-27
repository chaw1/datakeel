# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen version-scoped annotation reports and controlled inspection contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.annotation_models import AnnotationBatch, AnnotationQAResult, ReworkComparison
from datakeel.core.models import BoundaryModel


class AnnotationImportRequest(BoundaryModel):
    """Append one immutable annotation revision with an explicit retry identity."""

    version_id: str = Field(min_length=1)
    batch: AnnotationBatch
    idempotency_key: str = Field(min_length=1, max_length=200)
    name: str = Field(default="Annotation batch", min_length=1, max_length=200)
    rework_of: str | None = None


class AnnotationQualityReport(BoundaryModel):
    """Expose saved metrics and repair comparison without mutable database rows."""

    id: str
    dataset_id: str
    version_id: str
    name: str
    batch_digest: str
    sample_count: int
    annotation_count: int
    result: AnnotationQAResult
    comparison: ReworkComparison | None = None
    rework_of: str | None = None
    created_at: datetime


class SamplingRequest(BoundaryModel):
    """Choose normal single AQL inspection or a separately declared fixed fraction."""

    batch_id: str = Field(min_length=1)
    method: Literal["aql", "ratio"] = "aql"
    aql: float = Field(default=2.5, gt=0, le=10, allow_inf_nan=False)
    ratio: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    acceptance_number: int | None = Field(default=None, ge=0)
    seed: int = Field(default=0, ge=0, le=4_294_967_295)

    @model_validator(mode="after")
    def validate_method(self) -> "SamplingRequest":
        """Prevent ratio overrides from silently changing a standard table plan."""
        if self.method == "ratio" and (self.ratio is None or self.acceptance_number is None):
            message = "Ratio sampling requires ratio and acceptance_number"
            raise ValueError(message)
        if self.method == "aql" and (self.ratio is not None or self.acceptance_number is not None):
            message = "AQL sampling does not allow ratio or acceptance_number overrides"
            raise ValueError(message)
        return self


class SamplingPlan(BoundaryModel):
    """Bind reproducible selected units and table lookup to an immutable batch digest."""

    id: str
    batch_id: str
    dataset_id: str
    version_id: str
    batch_digest: str
    method: Literal["aql", "ratio"]
    lot_size: int
    sample_size: int
    sample_ids: tuple[str, ...]
    acceptance_number: int
    rejection_number: int
    code_letter: str | None = None
    effective_code_letter: str | None = None
    aql: float | None = None
    ratio: float | None = None
    seed: int
    created_at: datetime


class InspectionCheck(BoundaryModel):
    """Record one reviewed sampled unit; multiple errors count as one defective unit."""

    sample_id: str = Field(min_length=1)
    defective: bool
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def require_error_detail(self) -> "InspectionCheck":
        """Require explicit evidence whenever a unit is marked defective."""
        if self.defective and not self.reason.strip():
            message = "Defective units require an error detail"
            raise ValueError(message)
        return self


class AnnotationAcceptanceParams(BoundaryModel):
    """Review every frozen sampled unit through the signed controlled action boundary."""

    dataset_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    sampling_id: str = Field(min_length=1)
    checks: tuple[InspectionCheck, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_checks(self) -> "AnnotationAcceptanceParams":
        """Reject duplicate units instead of inflating an inspection count."""
        if len({item.sample_id for item in self.checks}) != len(self.checks):
            message = "Inspection checks must contain distinct sampled units"
            raise ValueError(message)
        return self


class SamplingInspection(BoundaryModel):
    """Archive the approved inspection decision and complete error details."""

    id: str
    action_plan_id: str
    sampling_id: str
    batch_id: str
    dataset_id: str
    version_id: str
    accepted: bool
    defective_count: int
    acceptance_number: int
    checks: tuple[InspectionCheck, ...]
    actor: str
    created_at: datetime


class AnnotationQualityOverview(BoundaryModel):
    """Read a dataset or exact version's annotation and inspection audit history."""

    dataset_id: str
    version_id: str | None
    latest: AnnotationQualityReport | None = None
    batches: tuple[AnnotationQualityReport, ...] = ()
    inspections: tuple[SamplingInspection, ...] = ()
    sampling_plans: tuple[SamplingPlan, ...] = ()


class ReworkItem(BoundaryModel):
    """Export either a statistical suspicion or a human inspection error with provenance."""

    item_id: str
    sample_id: str
    annotator_id: str | None = None
    code: str
    reason: str
    evidence: tuple[str, ...]
    inspection_id: str | None = None
