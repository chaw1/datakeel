# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only functions exposed to controlled tool callers."""

from pydantic import BaseModel, JsonValue

from datakeel.core.ask_models import AskRequest
from datakeel.core.errors import NotFoundError
from datakeel.core.kg_queries import KGExplainQuery, KGQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.annotation_functions import invoke_annotation_quality
from datakeel.ontology.annotation_parameters import AnnotationQualityParams
from datakeel.ontology.catalog_functions import invoke_catalog
from datakeel.ontology.catalog_parameters import ImpactParams, MetricListParams, MetricParams
from datakeel.ontology.evidence_functions import invoke_evidence
from datakeel.ontology.kg_functions import invoke_kg
from datakeel.ontology.models import FunctionResult, FunctionType, ObjectSet, PropertyFilter
from datakeel.ontology.parameters import (
    DatasetParams,
    EvidenceAssetParams,
    LineageParams,
    ListDatasetsParams,
    SearchFilesParams,
    TaskParams,
)
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.governance_service import get_quality, get_report
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.object_queries import evaluate
from datakeel.storage.task_queries import query_task

PARAMETER_MODELS: dict[str, type[BaseModel]] = {
    "list_datasets": ListDatasetsParams,
    "search_files": SearchFilesParams,
    "get_quality": DatasetParams,
    "get_lineage": LineageParams,
    "get_report": DatasetParams,
    "get_task": TaskParams,
    "query_evidence": EvidenceQuery,
    "get_evidence": EvidenceAssetParams,
    "explain_sample": EvidenceAssetParams,
    "ask_data": AskRequest,
    "list_metrics": MetricListParams,
    "explain_metric": MetricParams,
    "impact_of": ImpactParams,
    "query_kg": KGQuery,
    "explain_relation": KGExplainQuery,
    "annotation_quality": AnnotationQualityParams,
}


def function_definitions() -> list[FunctionType]:
    """Generate schema-bearing function descriptors from validated argument models."""
    return [
        FunctionType(
            id=name,
            input_schema=JsonDocument.model_validate(model.model_json_schema()),
            output_schema=JsonDocument.model_validate(FunctionResult.model_json_schema()),
            read_scope=f"{name}:read",
            handler="datakeel.ontology.functions.invoke_function",
        )
        for name, model in PARAMETER_MODELS.items()
    ]


def _result(function: str, refs: list[AssetRef], data: JsonValue) -> FunctionResult:
    return FunctionResult(function=function, asset_refs=refs, data=data)


def _list_datasets(db: Database, arguments: JsonDocument) -> FunctionResult:
    params = ListDatasetsParams.model_validate(arguments.root)
    datasets = list_datasets(db)[: params.limit]
    return _result(
        "list_datasets",
        [AssetRef(asset_id=value.id, display_name=value.name) for value in datasets],
        [value.model_dump(mode="json") for value in datasets],
    )


def _search_files(db: Database, arguments: JsonDocument) -> FunctionResult:
    params = SearchFilesParams.model_validate(arguments.root)
    filters: list[PropertyFilter] = []
    for field, value in (("modality", params.modality), ("quarantined", params.quarantined)):
        if value is not None:
            filters.append(PropertyFilter(field=field, value=value))
    if params.path is not None:
        filters.append(PropertyFilter(field="path", operator="contains", value=params.path))
    manifest = evaluate(
        db,
        ObjectSet(
            dataset_id=params.dataset_id,
            filters=filters,
            quality_min=params.quality_min,
            quality_max=params.quality_max,
            version_ids=[params.version_id] if params.version_id else [],
            limit=params.limit,
        ),
    )
    refs = [value.asset_ref for value in manifest.objects]
    if not refs and params.dataset_id:
        refs = [AssetRef(asset_id=params.dataset_id)]
    return _result("search_files", refs, manifest.model_dump(mode="json"))


def _dataset_result(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    params = DatasetParams.model_validate(arguments.root)
    value = (
        get_quality(db, params.dataset_id)
        if name == "get_quality"
        else get_report(db, params.dataset_id)
    )
    return _result(name, [AssetRef(asset_id=params.dataset_id)], value.model_dump(mode="json"))


def _lineage(db: Database, arguments: JsonDocument) -> FunctionResult:
    params = LineageParams.model_validate(arguments.root)
    value = get_graph(db, params.asset_id, params.direction, params.depth)
    refs = [
        AssetRef(
            asset_id=node.asset_id,
            asset_type=node.asset_type,
            namespace=node.namespace,
            version=node.version,
            display_name=node.display_name,
        )
        for node in value.nodes
    ]
    return _result(
        "get_lineage", refs or [AssetRef(asset_id=params.asset_id)], value.model_dump(mode="json")
    )


def invoke_function(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    """Validate and execute an allowlisted read without granting mutation capabilities."""
    if name in {"list_datasets", "search_files", "annotation_quality"}:
        return {
            "list_datasets": _list_datasets,
            "search_files": _search_files,
            "annotation_quality": invoke_annotation_quality,
        }[name](db, arguments)
    if name in {"get_quality", "get_report"}:
        return _dataset_result(db, name, arguments)
    if name == "get_lineage":
        return _lineage(db, arguments)
    if name in {
        "query_evidence",
        "get_evidence",
        "explain_sample",
        "ask_data",
        "list_metrics",
        "explain_metric",
        "impact_of",
        "query_kg",
        "explain_relation",
    }:
        handler = (
            invoke_kg
            if name in {"query_kg", "explain_relation"}
            else invoke_evidence
            if name in {"query_evidence", "get_evidence", "explain_sample"}
            else invoke_catalog
        )
        return handler(db, name, arguments)
    if name == "get_task":
        params = TaskParams.model_validate(arguments.root)
        value = query_task(db, params.task_id)
        return _result(
            name,
            [AssetRef(asset_type="task", asset_id=params.task_id)],
            value.model_dump(mode="json"),
        )
    msg = f"Unknown read function: {name}"
    raise NotFoundError(msg)
