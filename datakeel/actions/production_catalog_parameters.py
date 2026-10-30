# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed controlled actions for production vocabularies, models and prediction imports."""

from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.annotation_sampling import InspectionCheck
from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import (
    LabelMigration,
    PredictionFile,
    ProductionLabel,
    ProductionModel,
    ProductionTemplate,
)
from datakeel.core.production_team_models import PackageSamplingParams


class ProductionCatalogActionParams(BoundaryModel):
    """Require a client retry identity for every production catalog mutation."""

    request_id: str = Field(min_length=1, max_length=200)


class CreateLabelSetParams(ProductionCatalogActionParams):
    """Create/edit a vocabulary draft, or manage its reusable annotation template."""

    target: Literal["label_set", "template"] = "label_set"
    operation: Literal["create", "update", "delete"] = "create"
    label_set_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    name: str = Field(default="Labels", min_length=1, max_length=200)
    labels: tuple[ProductionLabel, ...] = ()
    previous_version: int | None = Field(default=None, ge=1)
    migration: tuple[LabelMigration, ...] = ()
    template: ProductionTemplate | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "CreateLabelSetParams":
        """Keep template writes inside the declared catalog action with explicit intent."""
        if self.target == "template" and self.template is None:
            message = "Template operations require a complete template definition"
            raise ValueError(message)
        if self.target == "label_set" and self.operation != "delete" and not self.labels:
            message = "Label sets require at least one label"
            raise ValueError(message)
        if (
            self.target == "label_set"
            and self.operation != "create"
            and (self.label_set_id is None or self.version is None)
        ):
            message = "Editing or deleting a draft requires label_set_id and version"
            raise ValueError(message)
        return self


class PublishLabelSetParams(ProductionCatalogActionParams):
    """Publish one immutable version after displaying its exact migration impact."""

    label_set_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class RegisterModelParams(ProductionCatalogActionParams):
    """Register an offline model or the provenance of imported external predictions."""

    model: ProductionModel


class UpdateModelParams(RegisterModelParams):
    """Replace a model definition only at the caller's expected catalog revision."""

    expected_revision: int = Field(ge=1)


class ImportPredictionsParams(ProductionCatalogActionParams):
    """Import COCO or normalized YOLO boxes independently for each source image."""

    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    format: Literal["coco", "yolo"]
    files: tuple[PredictionFile, ...] = Field(min_length=1, max_length=10000)
    category_mapping: dict[str, str] = Field(default_factory=dict)
    package_id: str | None = None


class RunPrelabelParams(ProductionCatalogActionParams):
    """Run a fake or cloud model; an estimate above ``budget`` needs approval, cloud stops there."""

    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    package_id: str | None = None
    budget: float = Field(default=0, ge=0, allow_inf_nan=False)


class FinalizeProjectParams(ProductionCatalogActionParams):
    """Freeze every approved task into an existing annotation batch and new version."""

    project_id: str = Field(min_length=1)
    name: str = Field(default="Production annotations", min_length=1, max_length=200)


class AcceptPackageParams(ProductionCatalogActionParams, PackageSamplingParams):
    """Inspect every P26-sampled unit of an approved team package, then accept or return it."""

    package_id: str = Field(min_length=1)
    checks: tuple[InspectionCheck, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_checks(self) -> "AcceptPackageParams":
        """Reject duplicate units instead of inflating an inspection count, as P26 does."""
        if len({item.sample_id for item in self.checks}) != len(self.checks):
            message = "Inspection checks must contain distinct sampled units"
            raise ValueError(message)
        return self


CATALOG_PARAMETER_TYPES: dict[str, type[ProductionCatalogActionParams]] = {
    "create_label_set": CreateLabelSetParams,
    "publish_label_set": PublishLabelSetParams,
    "register_model": RegisterModelParams,
    "update_model": UpdateModelParams,
    "import_predictions": ImportPredictionsParams,
    "run_prelabel": RunPrelabelParams,
    "finalize_project": FinalizeProjectParams,
    "accept_package": AcceptPackageParams,
}

CATALOG_POLICIES: dict[str, tuple[str, bool, str]] = {
    "create_label_set": ("production:manage", True, "Create annotation vocabulary or template"),
    "publish_label_set": ("production:manage", False, "Publish immutable vocabulary version"),
    "register_model": ("production:models", False, "Register an offline prelabel model"),
    "update_model": ("production:models", False, "Update an offline prelabel model"),
    "import_predictions": ("production:manage", True, "Import model-attributed revisions"),
    "run_prelabel": (
        "production:manage",
        True,
        "Run a prelabel model; cloud runs stop at the budget and need approval above it",
    ),
    "finalize_project": ("production:finalize", False, "Publish finalized production annotations"),
    "accept_package": ("production:accept", False, "Accept or return a package by sampling"),
}
