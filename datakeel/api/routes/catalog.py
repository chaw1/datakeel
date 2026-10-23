# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Paginated metadata navigation, table evidence, metric history, and bounded impact."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.catalog_models import (
    CatalogKind,
    CatalogObject,
    CatalogPage,
    CatalogQuery,
    CatalogTableDetail,
    ImpactResult,
)
from datakeel.core.metric_history_models import MetricHistory
from datakeel.core.metric_models import MetricCard
from datakeel.storage import catalog_queries, metric_store
from datakeel.storage.catalog_details import table_detail

router = APIRouter(prefix="/api/catalog", tags=["catalog"])
CatalogCollection = Literal[
    "sources", "tables", "columns", "metrics", "dimensions", "terms", "owners"
]
_COLLECTIONS: dict[str, CatalogKind] = {
    "sources": "source",
    "tables": "table",
    "columns": "column",
    "metrics": "metric",
    "dimensions": "dimension",
    "terms": "term",
    "owners": "owner",
}


@router.get("/impact")
def impact(
    db: DatabaseDependency,
    asset_id: Annotated[str, Query(min_length=1)],
    max_nodes: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> ImpactResult:
    """Follow the fixed downstream relationship directions for at most three hops."""
    return catalog_queries.impact(db, asset_id, max_nodes)


@router.get("/neighbors")
def neighbors(
    db: DatabaseDependency, asset_id: Annotated[str, Query(min_length=1)]
) -> ImpactResult:
    """Read the explicitly related metadata surrounding one catalog object."""
    catalog_queries.get_object(db, asset_id)
    return catalog_queries.neighbors(db, asset_id)


@router.get("/metrics/{metric_id}/history")
def metric_history(metric_id: str, db: DatabaseDependency) -> MetricHistory:
    """Read every persisted version of an existing metric in ascending order."""
    metric_store.get_metric(db, metric_id)
    return metric_store.metric_history_detail(db, metric_id)


@router.get("/metrics/{metric_id}")
def metric(metric_id: str, db: DatabaseDependency) -> MetricCard:
    """Read the current authoritative metric card, including unresolved reasons."""
    return metric_store.get_metric(db, metric_id)


@router.get("/tables/{asset_id:path}")
def table(asset_id: str, db: DatabaseDependency) -> CatalogTableDetail:
    """Read table fields, owners, semantic consumers, and adjacent relationships."""
    return table_detail(db, asset_id)


@router.get("/objects/{asset_id:path}")
def asset(asset_id: str, db: DatabaseDependency) -> CatalogObject:
    """Read a metadata object by its stable percent-encoded identity."""
    return catalog_queries.get_object(db, asset_id)


@router.get("/{collection}")
def collection(
    collection: CatalogCollection,
    query: Annotated[CatalogQuery, Query()],
    db: DatabaseDependency,
) -> CatalogPage:
    """List stable pages filtered by source, containing object, or case-insensitive name."""
    return catalog_queries.read_objects(
        db, query.model_copy(update={"kind": _COLLECTIONS[collection]})
    )
