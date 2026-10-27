# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-only entry points for explicitly supplied external metadata artifacts."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from datakeel.api.dependencies import DatabaseDependency
from datakeel.catalog.metadata_service import import_airflow, import_dbt, read_import_objects
from datakeel.core.catalog_models import CatalogPage
from datakeel.core.metadata_imports import (
    AirflowImportRequest,
    DbtImportRequest,
    MetadataImportReport,
)

router = APIRouter(prefix="/api/catalog/import", tags=["metadata-imports"])


@router.post("/dbt")
def dbt(request: DbtImportRequest, db: DatabaseDependency) -> MetadataImportReport:
    """Import decoded dbt artifacts without reading paths on the HTTP server."""
    return import_dbt(db, request)


@router.post("/airflow")
def airflow(request: AirflowImportRequest, db: DatabaseDependency) -> MetadataImportReport:
    """Import one offline Airflow REST v1 export supplied by the caller."""
    return import_airflow(db, request)


@router.get("/objects")
def objects(
    db: DatabaseDependency,
    kind: Literal[
        "source", "table", "column", "dag", "airflow_task", "exposure", "metric_draft", "job"
    ]
    | None = None,
    source_id: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> CatalogPage:
    """Browse imported orchestration and consumer nodes without changing old filters."""
    return read_import_objects(db, kind=kind, source_id=source_id, offset=offset, limit=limit)
