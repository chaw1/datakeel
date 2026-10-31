# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned annotation vocabularies, templates and offline prediction contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.image_orientation import CoordinateFrame
from datakeel.core.models import BoundaryModel
from datakeel.core.prelabel_models import (
    CloudModelConfig,
    ConfidenceThresholds,
    PrelabelCall,
    PrelabelDrop,
    PrelabelEstimate,
    PrelabelStop,
    TaskTier,
)
from datakeel.core.production_attributes import TemplateAttribute


class ProductionLabel(BoundaryModel):
    """Describe a stable label identity and its optional tree presentation."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent_id: str | None = None
    color: str | None = None
    shortcut: str | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class LabelMigration(BoundaryModel):
    """Declare how existing annotations are reviewed when label identities change."""

    operation: Literal["rename", "delete", "merge", "split"]
    source_ids: tuple[str, ...] = Field(min_length=1)
    target_ids: tuple[str, ...] = ()
    strategy: Literal["map", "drop", "manual"] = "map"
    reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_mapping(self) -> "LabelMigration":
        """Require explicit targets and manual decisions for ambiguous splits."""
        if len(set(self.source_ids)) != len(self.source_ids) or len(set(self.target_ids)) != len(
            self.target_ids
        ):
            message = "Migration source and target identities must be distinct"
            raise ValueError(message)
        valid = {
            "rename": len(self.source_ids) == 1 and len(self.target_ids) == 1,
            "delete": len(self.source_ids) == 1 and not self.target_ids,
            "merge": len(self.source_ids) > 1 and len(self.target_ids) == 1,
            "split": len(self.source_ids) == 1 and len(self.target_ids) > 1,
        }
        if not valid[self.operation]:
            message = "Migration source and target counts do not match its operation"
            raise ValueError(message)
        if self.operation == "delete" and self.strategy not in {"drop", "manual"}:
            message = "Deleted labels require drop or manual migration"
            raise ValueError(message)
        if self.operation == "split" and self.strategy != "manual":
            message = "Split labels require manual annotation review"
            raise ValueError(message)
        if self.operation in {"rename", "merge"} and self.strategy == "drop":
            message = "Rename and merge migrations require mapping or manual review"
            raise ValueError(message)
        return self


class LabelSet(BoundaryModel):
    """Keep one draft or immutable published vocabulary version."""

    id: str
    version: int = Field(ge=1)
    name: str
    labels: tuple[ProductionLabel, ...]
    published: bool = False
    previous_version: int | None = None
    migration: tuple[LabelMigration, ...] = ()
    affected_annotations: int = 0
    affected_revisions: int = 0
    created_at: datetime
    published_at: datetime | None = None


class ProductionTemplate(BoundaryModel):
    """Configure one supported core annotation representation and validation rules."""

    id: str
    name: str
    annotation_type: Literal["box", "polygon", "keypoints", "classification", "text_span"] = "box"
    component_config: dict[str, JsonValue] = Field(default_factory=dict)
    validation_rules: dict[str, JsonValue] = Field(default_factory=dict)
    attributes: tuple[TemplateAttribute, ...] = Field(default=(), max_length=50)
    revision: int = Field(default=1, ge=1)
    archived: bool = False

    @model_validator(mode="after")
    def distinct_attribute_keys(self) -> "ProductionTemplate":
        """Give every record or shape attribute one definition so forms and checks agree."""
        keys = [(field.target, field.key) for field in self.attributes]
        if len(set(keys)) != len(keys):
            message = "Template attribute keys must be distinct within each target"
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def supported_validation_rules(self) -> "ProductionTemplate":
        """Reject unsupported rules so saving never silently bypasses a configured constraint."""
        components = self.component_config.get("components")
        supported = {"box", "polygon", "classification", "text_span"}
        if components is not None and (
            not isinstance(components, list)
            or not components
            or any(not isinstance(value, str) or value not in supported for value in components)
            or len({str(value) for value in components}) != len(components)
        ):
            message = "Template components must be distinct supported annotation types"
            raise ValueError(message)
        if set(self.validation_rules) - {"min_annotations", "max_annotations"}:
            message = "Supported template rules are min_annotations and max_annotations"
            raise ValueError(message)
        minimum = self.validation_rules.get("min_annotations", 0)
        maximum = self.validation_rules.get("max_annotations", 100000)
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or not 0 <= minimum <= maximum
        ):
            message = (
                "Template annotation bounds must be nonnegative integers with minimum <= maximum"
            )
            raise ValueError(message)
        return self


class ProductionModel(BoundaryModel):
    """Register an offline provider, imported-prediction provenance or a cloud vision model.

    ``unit_price`` is a per-image charge; cloud models add token prices from ``cloud``.
    """

    id: str
    name: str
    version: str
    provider: Literal["fake", "import", "cloud"]
    capabilities: tuple[
        Literal["box", "polygon", "keypoints", "classification", "text_span"], ...
    ] = ("box",)
    unit_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    currency: str = "USD"
    revision: int = Field(default=1, ge=1)
    cloud: CloudModelConfig | None = None

    @model_validator(mode="after")
    def cloud_configuration(self) -> "ProductionModel":
        """Give cloud models exactly one endpoint and keep it off offline providers."""
        if (self.provider == "cloud") != (self.cloud is not None):
            message = "Cloud models require cloud settings; other providers must omit them"
            raise ValueError(message)
        if self.provider == "cloud" and not {"box", "classification"} & set(self.capabilities):
            message = "Cloud prelabel models support box and classification capabilities"
            raise ValueError(message)
        return self

    def estimate_cost(self, count: int) -> float:
        """Compare decimal prices without rounding overruns at an exact declared budget."""
        return float(Decimal(str(self.unit_price)) * count)


class PredictionFile(BoundaryModel):
    """Carry uploaded text rather than letting action execution read arbitrary local paths."""

    filename: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=10_000_000)
    sample_id: str | None = None
    image_width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    image_height: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    coordinate_frame: CoordinateFrame | None = Field(
        default=None,
        description=(
            "Pixel frame of the coordinates: display (EXIF Orientation applied, the default) "
            "or stored (raw pixel order). Omitted: COCO is inferred from the image width/height."
        ),
    )


class PredictionFailure(BoundaryModel):
    """Report one file's complete rejection while preserving other files in the batch."""

    filename: str
    sample_id: str | None = None
    code: str
    message: str


class ParsedPrediction(BoundaryModel):
    """Pass a validated prediction and confidence across the parser/storage boundary."""

    filename: str
    annotation: AnnotationRecord
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    object_confidences: tuple[float, ...] = ()


class PredictionImportResult(BoundaryModel):
    """Expose partial success without hiding empty, malformed or unmappable files."""

    revision_ids: tuple[str, ...] = ()
    failures: tuple[PredictionFailure, ...] = ()


class PrelabelRun(BoundaryModel):
    """Archive deterministic offline model attribution and measured execution totals."""

    id: str
    project_id: str
    package_id: str | None
    model_id: str
    model_name: str
    model_version: str
    revision_ids: tuple[str, ...]
    failures: tuple[PredictionFailure, ...] = ()
    cost: float = Field(ge=0, allow_inf_nan=False)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    confidences: tuple[float, ...]
    created_at: datetime
    provider: Literal["fake", "import", "cloud"] | None = None
    currency: str | None = None
    budget: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estimate: PrelabelEstimate | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    calls: tuple[PrelabelCall, ...] = ()
    dropped: tuple[PrelabelDrop, ...] = ()
    skipped_sample_ids: tuple[str, ...] = ()
    human_edited_sample_ids: tuple[str, ...] = ()
    stopped: PrelabelStop | None = None
    thresholds: ConfidenceThresholds | None = None
    tiers: tuple[TaskTier, ...] = ()
    held_drafts: int = Field(
        default=0, ge=0, description="Tasks someone held: only a draft was written, never routed."
    )
    status: Literal["running", "completed", "failed", "abandoned"] = "completed"
    actor: str | None = None
    plan_id: str | None = None
    planned_images: int = Field(default=0, ge=0)
    completed_images: int = Field(default=0, ge=0)
    failed_images: int = Field(default=0, ge=0)
    updated_at: datetime | None = None
