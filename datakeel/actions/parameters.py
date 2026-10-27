# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated canonical parameter schemas for built-in controlled actions."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator

from datakeel.actions.catalog_parameters import (
    ImportCatalogParams,
    RestoreCatalogParams,
    RollbackMetricParams,
    RollbackTermParams,
    UpdateMetricParams,
    UpdateTermParams,
)
from datakeel.actions.dq_parameters import (
    ChangeQualityIssueParams,
    CreateQualityRuleParams,
    DeleteQualityRuleParams,
    RunQualityRuleParams,
    UpdateQualityRuleParams,
)
from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import AssertionStatus
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.models import ObjectSet, PropertyFilter
from datakeel.pipeline import Pipeline, validate_pipeline


class SelectionParams(BoundaryModel):
    """Resolve a file ObjectSet to a frozen manifest before changing state."""

    selection: ObjectSet


class VersionParams(SelectionParams):
    """Publish the exact selected files as a new immutable version."""

    name: str | None = None


class DecideAssertionsParams(BoundaryModel):
    """Review exact active assertions without accepting caller-supplied actor privileges."""

    assertion_ids: tuple[Annotated[str, Field(min_length=1)], ...] = Field(
        min_length=1, max_length=10000
    )
    status: AssertionStatus
    reason: str = Field(default="User decision", min_length=1, max_length=2000)

    @field_validator("assertion_ids")
    @classmethod
    def canonical_identities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Bind duplicate and reordered input identities to the same canonical intent."""
        return tuple(sorted(set(values)))


class PipelineParams(BoundaryModel):
    """Schedule a validated pipeline against one frozen dataset manifest."""

    dataset_id: str
    pipeline: Pipeline | None = None
    version_id: str | None = None
    shards: int = Field(default=1, ge=1, le=128)
    queue: Literal["cpu", "io", "gpu"] = "cpu"


class MetadataParams(BoundaryModel):
    """Replace dataset metadata with a mandatory audit reason."""

    dataset_id: str
    values: dict[str, JsonValue]
    reason: str = Field(min_length=1)


class ExportParams(BoundaryModel):
    """Write a local export artifact under the configured exports directory."""

    dataset_id: str
    format: Literal["croissant", "openlineage"] = "croissant"
    destination: str | None = None


PARAMETER_TYPES: dict[str, type[BoundaryModel]] = {
    "quarantine_files": SelectionParams,
    "unquarantine_files": SelectionParams,
    "delete_files": SelectionParams,
    "create_version_from_selection": VersionParams,
    "run_pipeline": PipelineParams,
    "run_kg_extraction": RunKGExtractionParams,
    "save_metadata": MetadataParams,
    "export_dataset": ExportParams,
    "decide_assertions": DecideAssertionsParams,
    "import_catalog": ImportCatalogParams,
    "restore_catalog": RestoreCatalogParams,
    "update_metric": UpdateMetricParams,
    "rollback_metric": RollbackMetricParams,
    "update_term": UpdateTermParams,
    "rollback_term": RollbackTermParams,
    "create_quality_rule": CreateQualityRuleParams,
    "update_quality_rule": UpdateQualityRuleParams,
    "delete_quality_rule": DeleteQualityRuleParams,
    "run_quality_rule": RunQualityRuleParams,
    "change_quality_issue": ChangeQualityIssueParams,
}


def parse_params(action_type: str, params: JsonDocument) -> BoundaryModel:
    """Reject undeclared actions and parameters before any persisted mutation."""
    schema = PARAMETER_TYPES.get(action_type)
    if schema is None:
        msg = f"Unknown action: {action_type}"
        raise ValidationError(msg)
    value = schema.model_validate(params.root)
    if isinstance(value, PipelineParams) and value.pipeline is not None:
        validate_pipeline(value.pipeline)
    return value


def selection_for(params: BoundaryModel) -> ObjectSet:
    """Derive the complete affected asset query for one parameter schema."""
    if isinstance(params, SelectionParams):
        if params.selection.object_type not in {"file", "artifact"}:
            msg = "This action requires a file or artifact selection"
            raise ValidationError(msg)
        if params.selection.include_deleted:
            msg = "Deleted files cannot be action targets"
            raise ValidationError(msg)
        return params.selection
    if isinstance(params, PipelineParams | RunKGExtractionParams):
        return ObjectSet(
            dataset_id=params.dataset_id,
            limit=10000,
            version_ids=[params.version_id] if params.version_id else [],
            filters=[PropertyFilter(field="id", operator="in", value=list(params.file_ids))]
            if isinstance(params, RunKGExtractionParams) and params.file_ids
            else [],
        )
    if isinstance(params, ExportParams):
        return ObjectSet(dataset_id=params.dataset_id, limit=10000)
    if isinstance(params, MetadataParams):
        return ObjectSet(
            object_type="dataset",
            dataset_id=params.dataset_id,
            filters=[PropertyFilter(field="id", value=params.dataset_id)],
        )
    msg = "Action parameters have no target selection"
    raise ValidationError(msg)
