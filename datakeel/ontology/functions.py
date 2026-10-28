# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only functions exposed to controlled tool callers."""

from pydantic import BaseModel, JsonValue

from datakeel.core.ask_models import AskRequest
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.kg_queries import KGExplainQuery, KGQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.standard_reporting_models import StandardCoverageParams, StandardUsageParams
from datakeel.core.training_governance import TrainingQualityQuery
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.lineage.models import GraphNode, GraphView
from datakeel.ontology.annotation_functions import invoke_annotation_quality
from datakeel.ontology.annotation_parameters import AnnotationQualityParams
from datakeel.ontology.catalog_functions import invoke_catalog
from datakeel.ontology.catalog_parameters import ImpactParams, MetricListParams, MetricParams
from datakeel.ontology.data_asset_access import requested_refs
from datakeel.ontology.dq_functions import QualityRulesParams, TableQualityParams, invoke_quality
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
from datakeel.ontology.standard_functions import invoke_standard
from datakeel.ontology.tool_refs import extract_refs
from datakeel.ontology.training_functions import invoke_training
from datakeel.storage.data_asset_access import require_access, skip_protected
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
    "query_standard_coverage": StandardCoverageParams,
    "list_standard_usage": StandardUsageParams,
    "list_quality_rules": QualityRulesParams,
    "get_table_quality": TableQualityParams,
    "annotation_quality": AnnotationQualityParams,
    "get_training_quality": TrainingQualityQuery,
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


def _list_datasets(db: Database, arguments: JsonDocument, caller: AccessContext) -> FunctionResult:
    params = ListDatasetsParams.model_validate(arguments.root)
    datasets = list_datasets(db)
    skipped = skip_protected(
        db,
        [
            (value.id, (AssetRef(asset_id=value.id), *extract_refs(value.model_dump(mode="json"))))
            for value in datasets
        ],
        caller,
    )
    hidden: set[str] = set(skipped.ids) if skipped else set()
    visible = [value for value in datasets if value.id not in hidden][: params.limit]
    return FunctionResult(
        function="list_datasets",
        asset_refs=[AssetRef(asset_id=value.id, display_name=value.name) for value in visible],
        data=[value.model_dump(mode="json") for value in visible],
        skipped=skipped,
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


def _dataset_result(
    db: Database, name: str, arguments: JsonDocument, access: AccessContext | None = None
) -> FunctionResult:
    params = DatasetParams.model_validate(arguments.root)
    value = (
        get_quality(db, params.dataset_id, access=access)
        if name == "get_quality"
        else get_report(db, params.dataset_id, access=access)
    )
    return _result(name, [AssetRef(asset_id=params.dataset_id)], value.model_dump(mode="json"))


def _node_ref(node: GraphNode) -> AssetRef:
    return AssetRef(
        asset_id=node.asset_id,
        asset_type=node.asset_type,
        namespace=node.namespace,
        version=node.version,
        display_name=node.display_name,
    )


def _connected(value: GraphView, root: str) -> set[str]:
    """Node IDs still linked to the requested asset after protected nodes are removed."""
    start = {node.id for node in value.nodes if node.asset_id == root}
    if not start:
        return {node.id for node in value.nodes}
    links: dict[str, set[str]] = {}
    for edge in value.edges:
        links.setdefault(edge.source, set()).add(edge.target)
        links.setdefault(edge.target, set()).add(edge.source)
    seen, queue = set(start), list(start)
    while queue:
        for other in links.get(queue.pop(), set()) - seen:
            seen.add(other)
            queue.append(other)
    return seen


def _without(value: GraphView, hidden: set[str]) -> GraphView:
    """Remove nodes and events by ID, plus every event or edge that touches them."""
    assets = {node.asset_id for node in value.nodes if node.id in hidden}
    events = [
        event
        for event in value.events
        if event.event_id not in hidden
        and not any(ref.asset_id in assets for ref in (*event.inputs, *event.outputs))
    ]
    kept = {event.event_id for event in events}
    return value.model_copy(
        update={
            "nodes": [node for node in value.nodes if node.id not in hidden],
            "events": events,
            "edges": [
                edge
                for edge in value.edges
                if edge.source not in hidden
                and edge.target not in hidden
                and (edge.event_id is None or edge.event_id in kept or edge.kind == "catalog")
            ],
        }
    )


def _readable_graph(
    db: Database, value: GraphView, caller: AccessContext, root: str
) -> FunctionResult:
    """Drop protected nodes, the events and edges touching them, and what they disconnect."""
    entries = [(node.id, (_node_ref(node),)) for node in value.nodes]
    entries += [
        (event.event_id, tuple(extract_refs(event.model_dump(mode="json"))))
        for event in value.events
    ]
    skipped = skip_protected(db, entries, caller)
    graph = value
    if skipped is not None:
        graph = _without(value, set(skipped.ids))
        reachable = _connected(graph, root)
        graph = _without(graph, {node.id for node in graph.nodes if node.id not in reachable})
    return FunctionResult(
        function="get_lineage",
        asset_refs=[_node_ref(node) for node in graph.nodes],
        data=graph.model_dump(mode="json"),
        skipped=skipped,
    )


def _lineage(db: Database, arguments: JsonDocument, caller: AccessContext) -> FunctionResult:
    params = LineageParams.model_validate(arguments.root)
    value = get_graph(db, params.asset_id, params.direction, params.depth)
    result = _readable_graph(db, value, caller, params.asset_id)
    if not result.asset_refs:
        return result.model_copy(update={"asset_refs": [AssetRef(asset_id=params.asset_id)]})
    return result


def invoke_function(
    db: Database,
    name: str,
    arguments: JsonDocument,
    *,
    access: AccessContext | None = None,
) -> FunctionResult:
    """Validate and execute an allowlisted read without granting mutation capabilities."""
    caller = access or AccessContext(actor="local", entry="agent", scope="query")
    if name in PARAMETER_MODELS:
        PARAMETER_MODELS[name].model_validate(arguments.root)
    require_access(db, requested_refs(name, arguments), caller, record=False)
    if name in {"ask_data", "list_metrics"}:
        result = invoke_catalog(db, name, arguments, access=caller)
    elif name == "list_datasets":
        result = _list_datasets(db, arguments, caller)
    elif name == "get_training_quality":
        result = invoke_training(db, arguments, access=caller)
    elif name in {"get_quality", "get_report"}:
        result = _dataset_result(db, name, arguments, caller)
    elif name == "get_lineage":
        result = _lineage(db, arguments, caller)
    elif name in {"query_kg", "explain_relation"}:
        result = invoke_kg(db, name, arguments, access=caller)
    elif name in {"query_evidence", "get_evidence", "explain_sample"}:
        result = invoke_evidence(db, name, arguments, access=caller)
    else:
        result = _invoke_function(db, name, arguments)
    require_access(db, (*result.asset_refs, *extract_refs(result.data)), caller)
    return result


def _invoke_function(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    if name == "search_files":
        return _search_files(db, arguments)
    if name == "annotation_quality":
        return invoke_annotation_quality(db, arguments)
    if name in {
        "query_evidence",
        "get_evidence",
        "explain_sample",
        "ask_data",
        "explain_metric",
        "impact_of",
        "query_kg",
        "explain_relation",
        "query_standard_coverage",
        "list_standard_usage",
        "list_quality_rules",
        "get_table_quality",
    }:
        handler = (
            invoke_standard
            if name in {"query_standard_coverage", "list_standard_usage"}
            else invoke_quality
            if name in {"list_quality_rules", "get_table_quality"}
            else invoke_kg
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
