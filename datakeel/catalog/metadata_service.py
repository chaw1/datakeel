# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application services for artifact imports and extended catalog navigation."""

import httpx

from datakeel.catalog.importers.airflow import prepare_airflow
from datakeel.catalog.importers.airflow_rest import AirflowConnection, fetch_airflow_export
from datakeel.catalog.importers.dbt import dbt_scope, prepare_dbt
from datakeel.core.catalog_models import CatalogPage
from datakeel.core.metadata_imports import (
    AirflowImportRequest,
    AirflowSource,
    DbtImportRequest,
    MetadataImportReport,
)
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.metadata_store import publish_metadata, publish_metadata_from_prior


def import_dbt(
    db: Database, request: DbtImportRequest, actor: str = "local-user"
) -> MetadataImportReport:
    """Validate artifacts before atomically publishing their independent source scope.

    Without catalog.json the import is prepared inside the write transaction, against
    the version it replaces, so the previous reflected columns are carried over.
    """
    if request.catalog is not None:
        return publish_metadata(db, prepare_dbt(request), actor)
    return publish_metadata_from_prior(
        db, dbt_scope(request.source_id), lambda prior: prepare_dbt(request, prior), actor
    )


def import_airflow(
    db: Database, request: AirflowImportRequest, actor: str = "local-user"
) -> MetadataImportReport:
    """Import an offline export without constructing an Airflow client."""
    return publish_metadata(db, prepare_airflow(request), actor)


def import_airflow_api(
    db: Database,
    source: AirflowSource,
    connection: AirflowConnection,
    transport: httpx.BaseTransport | None = None,
) -> MetadataImportReport:
    """Read the configured REST v1 scheduler, then publish exactly like an offline export."""
    document = fetch_airflow_export(connection, source.dag_ids, transport)
    request = AirflowImportRequest(source_id=source.source_id, name=source.name, document=document)
    return import_airflow(db, request, source.actor)


def read_import_objects(
    db: Database,
    *,
    kind: str | None = None,
    source_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> CatalogPage:
    """Page imported orchestration objects using the same catalog fact projection."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    items = tuple(
        item
        for item in snapshot.objects
        if (kind is None or item.asset_ref.asset_type == kind)
        and (source_id is None or item.source_id == source_id)
        and (
            "integration" in item.properties.root
            or item.asset_ref.asset_type
            in {"metric_draft", "dag", "airflow_task", "exposure", "job"}
        )
    )
    return CatalogPage(
        items=items[offset : offset + limit], total=len(items), offset=offset, limit=limit
    )
