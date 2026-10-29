# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply short business mutations inside the controlled action transaction."""

import json
from collections.abc import Callable
from types import UnionType
from typing import Any

from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import CatalogActionParams
from datakeel.actions.data_asset_parameters import DataAssetActionParams
from datakeel.actions.datasheet_parameters import GenerateDatasheetParams, PublishDatasheetParams
from datakeel.actions.dq_parameters import QualityActionParams
from datakeel.actions.identity_parameters import IdentityActionParams
from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.llm_data_parameters import CleanTrainingParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.parameters import (
    DecideAssertionsParams,
    MetadataParams,
    PipelineParams,
    parse_params,
)
from datakeel.actions.production_catalog_parameters import ProductionCatalogActionParams
from datakeel.actions.production_parameters import ProductionActionParams
from datakeel.actions.release_parameters import PublishReleaseParams
from datakeel.actions.standard_parameters import StandardActionParams
from datakeel.core.annotation_sampling import AnnotationAcceptanceParams
from datakeel.core.custom_operators import SubmitCustomOperatorParams
from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.governance import compliance_score, validate_metadata
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.action_selection import change_file_state, selected_files, single_dataset
from datakeel.storage.annotation_actions import inspect_action
from datakeel.storage.catalog_actions import execute_catalog_action
from datakeel.storage.custom_store import approve_custom_operator
from datakeel.storage.custom_validation import validate_custom_pipeline
from datakeel.storage.data_asset_actions import execute_data_asset_action
from datakeel.storage.database import DatasetRow, MetadataChangeRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.datasets import latest_files
from datakeel.storage.datasheet_actions import execute_datasheet
from datakeel.storage.dq_actions import execute_quality_action
from datakeel.storage.evidence_actions import decide_action
from datakeel.storage.identity_actions import execute_identity_action
from datakeel.storage.kg_store import schedule_extraction
from datakeel.storage.llm_data_actions import execute_training_clean
from datakeel.storage.production_actions import execute_production_action
from datakeel.storage.production_catalog_actions import (
    execute_catalog_action as execute_production_catalog,
)
from datakeel.storage.release_actions import publish_release
from datakeel.storage.standard_changes import execute_standard_action


def _metadata(session: Session, params: MetadataParams) -> OperationResult:
    dataset = session.get(DatasetRow, params.dataset_id, with_for_update=True)
    if dataset is None:
        msg = "Dataset no longer exists"
        raise NotFoundError(msg)
    if dataset.template:
        validate_metadata(dataset.template, params.values)
    previous = dataset.metadata_values
    for field in sorted(previous.keys() | params.values.keys()):
        before, after = previous.get(field), params.values.get(field)
        if json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True) or (
            field in previous
        ) != (field in params.values):
            session.add(
                MetadataChangeRow(
                    dataset_id=dataset.id,
                    field=field,
                    before=before,
                    after=after,
                    source="action",
                    reason=params.reason,
                )
            )
    dataset.metadata_values = params.values
    dataset.compliance = compliance_score(
        dataset.name, latest_files(session, dataset), params.values, dataset.template
    ).model_dump(mode="json", exclude_none=True)
    return OperationResult(outputs=[AssetRef(asset_id=dataset.id)], details={"before": previous})


def _pipeline(session: Session, plan: ActionPlan, params: PipelineParams) -> OperationResult:
    validate_shards(params.pipeline, params.shards)
    validate_custom_pipeline(session, params.pipeline)
    files = selected_files(session, plan)
    task = TaskRow(
        dataset_id=params.dataset_id,
        idempotency_key=f"action:{plan.id}",
        total_shards=params.shards,
        queue=params.queue,
        input_version_id=params.version_id,
        pipeline=params.pipeline.model_dump(mode="json") if params.pipeline else None,
    )
    session.add(task)
    session.flush()
    for ordinal in range(params.shards):
        session.add(
            ShardRow(
                task_id=task.id,
                ordinal=ordinal,
                inputs=[item.model_dump(mode="json") for item in files[ordinal :: params.shards]],
            )
        )
    return OperationResult(task_id=task.id)


# Parameter families whose own module performs the whole mutation, checked in order.
_TYPED_ACTIONS: tuple[
    tuple[type | UnionType, Callable[[Session, ActionPlan, Any], OperationResult]], ...
] = (
    (CleanTrainingParams, execute_training_clean),
    (IdentityActionParams, execute_identity_action),
    (ProductionActionParams, execute_production_action),
    (ProductionCatalogActionParams, execute_production_catalog),
    (DataAssetActionParams, execute_data_asset_action),
    (QualityActionParams, execute_quality_action),
    (AnnotationAcceptanceParams, inspect_action),
    (GenerateDatasheetParams | PublishDatasheetParams, execute_datasheet),
    (StandardActionParams, execute_standard_action),
    (SubmitCustomOperatorParams, approve_custom_operator),
    (PublishReleaseParams, publish_release),
    (CatalogActionParams, execute_catalog_action),
    (DecideAssertionsParams, decide_action),
)


def execute_business(session: Session, plan: ActionPlan) -> OperationResult:
    """Mutate a validated plan without opening or committing another transaction."""
    params = parse_params(plan.action_type, JsonDocument(plan.canonical_params))
    for kind, handler in _TYPED_ACTIONS:
        if isinstance(params, kind):
            return handler(session, plan, params)
    if plan.action_type in {"quarantine_files", "unquarantine_files", "delete_files"}:
        change_file_state(session, plan)
        outputs = (
            []
            if plan.action_type == "delete_files"
            else [item.asset_ref for item in plan.manifest.objects]
        )
        return OperationResult(outputs=outputs)
    if plan.action_type == "create_version_from_selection":
        dataset_id = single_dataset(plan)
        version = VersionRow(
            dataset_id=dataset_id,
            manifest=[item.model_dump(mode="json") for item in selected_files(session, plan)],
        )
        session.add(version)
        session.flush()
        return OperationResult(
            outputs=[AssetRef(asset_type="version", asset_id=version.id, version=version.id)]
        )
    return _additional_action(session, plan, params)


def _additional_action(session: Session, plan: ActionPlan, params: object) -> OperationResult:
    if isinstance(params, MetadataParams):
        return _metadata(session, params)
    if isinstance(params, PipelineParams):
        return _pipeline(session, plan, params)
    if isinstance(params, RunKGExtractionParams):
        return schedule_extraction(session, plan, params)
    msg = "No in-database handler for this action"
    raise NotFoundError(msg)
