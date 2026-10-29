# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed controlled actions for production vocabularies, models and prediction imports."""

from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import (
    LabelMigration,
    PredictionFile,
    ProductionLabel,
    ProductionModel,
    ProductionTemplate,
)


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
    """Run the deterministic free model, requiring approval for a declared budget overrun."""

    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    package_id: str | None = None
    budget: float = Field(default=0, ge=0, allow_inf_nan=False)


class FinalizeProjectParams(ProductionCatalogActionParams):
    """Freeze every approved task into an existing annotation batch and new version."""

    project_id: str = Field(min_length=1)
    name: str = Field(default="Production annotations", min_length=1, max_length=200)


CATALOG_PARAMETER_TYPES: dict[str, type[ProductionCatalogActionParams]] = {
    "create_label_set": CreateLabelSetParams,
    "publish_label_set": PublishLabelSetParams,
    "register_model": RegisterModelParams,
    "update_model": UpdateModelParams,
    "import_predictions": ImportPredictionsParams,
    "run_prelabel": RunPrelabelParams,
    "finalize_project": FinalizeProjectParams,
}

CATALOG_POLICIES: dict[str, tuple[str, bool, str]] = {
    "create_label_set": ("production:manage", True, "Create annotation vocabulary or template"),
    "publish_label_set": ("production:manage", False, "Publish immutable vocabulary version"),
    "register_model": ("production:models", False, "Register an offline prelabel model"),
    "update_model": ("production:models", False, "Update an offline prelabel model"),
    "import_predictions": ("production:manage", True, "Import model-attributed revisions"),
    "run_prelabel": ("production:manage", True, "Run deterministic offline prelabel model"),
    "finalize_project": ("production:finalize", False, "Publish finalized production annotations"),
}
