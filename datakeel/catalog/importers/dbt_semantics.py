# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retain dbt semantic resources as drafts, deriving only provably simple definitions."""

from pydantic import Field

from datakeel.catalog.importers.dbt_models import ArtifactModel, DbtNode, stable_resource
from datakeel.catalog.importers.dbt_objects import resource_owner
from datakeel.core.catalog_canonical import document_hash
from datakeel.core.catalog_identity import catalog_id, catalog_segments
from datakeel.core.catalog_models import CatalogObject
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import DbtImportRequest, MetricDraft
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime
from datakeel.core.models import AssetRef, JsonDocument

_AGGREGATIONS: frozenset[str] = frozenset({"sum", "count", "avg", "min", "max", "count_distinct"})


class DbtMeasure(ArtifactModel):
    """Read one dbt semantic measure without treating arbitrary expressions as columns."""

    name: str
    agg: str
    expr: str | int | float | None = None
    agg_params: JsonDocument | None = None
    non_additive_dimension: JsonDocument | None = None
    agg_time_dimension: str | None = None


class DbtDefaults(ArtifactModel):
    """Read a semantic model's declared aggregation time dimension."""

    agg_time_dimension: str | None = None


class DbtSemanticModel(DbtNode):
    """Read the narrow semantic fields required for safe simple metric conversion."""

    measures: tuple[DbtMeasure, ...] = ()
    defaults: DbtDefaults = Field(default_factory=DbtDefaults)
    dimensions: tuple[JsonDocument, ...] = ()


def _resources(request: DbtImportRequest, key: str) -> tuple[JsonDocument, ...]:
    resources = request.manifest.root.get(key, {})
    if not isinstance(resources, dict):
        msg = f"dbt manifest {key} must be an object"
        raise ValidationError(msg)
    return tuple(stable_resource(JsonDocument.model_validate(raw)) for raw in resources.values())


def _simple_measure(raw: JsonDocument) -> str | None:
    if raw.root.get("type") != "simple" or raw.root.get("filter"):
        return None
    params = raw.root.get("type_params")
    if not isinstance(params, dict):
        return None
    measure = params.get("measure")
    if isinstance(measure, str):
        return measure
    if (
        isinstance(measure, dict)
        and not measure.get("filter")
        and not measure.get("join_to_timespine")
        and measure.get("fill_nulls_with") is None
    ):
        name = measure.get("name")
        return name if isinstance(name, str) else None
    return None


def _metric_time(semantic: DbtSemanticModel, name: str) -> MetricTime | None:
    dimensions = [
        dimension for dimension in semantic.dimensions if dimension.root.get("name") == name
    ]
    if len(dimensions) != 1 or dimensions[0].root.get("type") != "time":
        return None
    dimension = dimensions[0].root
    params = dimension.get("type_params")
    granularity = params.get("time_granularity") if isinstance(params, dict) else None
    column = dimension.get("expr") or name
    if not isinstance(column, str) or granularity not in {"day", "month", "quarter", "year"}:
        return None
    return MetricTime.model_validate({"column": column, "granularity": granularity})


def _definition(
    raw: JsonDocument,
    semantic: DbtSemanticModel,
    measure: DbtMeasure,
    table: CatalogObject,
) -> MetricDefinition | None:
    metric = DbtNode.model_validate(raw.root)
    owner = resource_owner(metric) or resource_owner(semantic)
    time = measure.agg_time_dimension or semantic.defaults.agg_time_dimension
    columns = table.properties.root.get("columns")
    column = str(measure.expr) if measure.expr is not None else measure.name
    if not owner or not time or not isinstance(columns, dict):
        return None
    metric_time = _metric_time(semantic, time)
    if (
        column not in columns
        or metric_time is None
        or metric_time.column not in columns
        or measure.agg not in _AGGREGATIONS
        or measure.agg_params is not None
        or measure.non_additive_dimension is not None
    ):
        return None
    aggregation = Measure.model_validate(
        {
            "table": table.asset_ref.asset_id,
            "column": catalog_id(*catalog_segments(table.asset_ref.asset_id), column),
            "aggregation": measure.agg,
        }
    )
    return MetricDefinition(
        id=metric.unique_id,
        name=metric.name,
        description=metric.description,
        owner=owner,
        measure=aggregation,
        time=metric_time.model_copy(
            update={
                "column": catalog_id(
                    *catalog_segments(table.asset_ref.asset_id), metric_time.column
                )
            }
        ),
    )


def _metric_definition(
    raw: JsonDocument,
    semantics: tuple[DbtSemanticModel, ...],
    tables: dict[str, CatalogObject],
) -> MetricDefinition | None:
    name = _simple_measure(raw)
    matches = [
        (semantic, measure)
        for semantic in semantics
        for measure in semantic.measures
        if measure.name == name
    ]
    if len(matches) != 1:
        return None
    semantic, measure = matches[0]
    model_tables = [tables[parent] for parent in semantic.depends_on.nodes if parent in tables]
    if len(model_tables) != 1:
        return None
    return _definition(raw, semantic, measure, model_tables[0])


def _source_fingerprint(
    raw: JsonDocument,
    semantics: tuple[JsonDocument, ...],
    definition: MetricDefinition | None,
) -> str:
    document = JsonDocument.model_validate(
        {
            "resource": raw.root,
            "semantic_models": [item.root for item in sorted(semantics, key=document_hash)],
            "definition": definition.model_dump(mode="json") if definition else None,
        }
    )
    return document_hash(document)


def metric_drafts(
    request: DbtImportRequest, tables: dict[str, CatalogObject]
) -> tuple[CatalogObject, ...]:
    """Generate isolated unapproved drafts and retain every original semantic declaration."""
    raw_semantics = _resources(request, "semantic_models")
    semantics = tuple(DbtSemanticModel.model_validate(raw.root) for raw in raw_semantics)
    result: list[CatalogObject] = []
    for raw in (*raw_semantics, *_resources(request, "metrics")):
        node = DbtNode.model_validate(raw.root)
        definition = _metric_definition(raw, semantics, tables)
        draft = MetricDraft(
            unique_id=node.unique_id,
            description=node.description,
            definition=definition,
            raw=raw,
            source_fingerprint=_source_fingerprint(raw, raw_semantics, definition),
        )
        result.append(
            CatalogObject(
                asset_ref=AssetRef(
                    asset_type="metric_draft",
                    asset_id=catalog_id(request.source_id, "dbt-draft", node.unique_id),
                    display_name=node.name,
                ),
                name=node.name,
                source_id=request.source_id,
                properties=JsonDocument.model_validate(draft.model_dump(mode="json")),
            )
        )
    return tuple(result)
