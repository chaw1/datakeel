# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application services for artifact imports and extended catalog navigation."""

import httpx

from datakeel.catalog.importers.airflow import prepare_airflow
from datakeel.catalog.importers.airflow_rest import AirflowConnection, fetch_airflow_export
from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.core.metadata_imports import (
    AirflowImportRequest,
    AirflowSource,
    DbtImportRequest,
    MetadataImportReport,
)
from datakeel.storage.database import Database
from datakeel.storage.metadata_store import publish_metadata


def import_dbt(
    db: Database, request: DbtImportRequest, actor: str = "local-user"
) -> MetadataImportReport:
    """Validate artifacts before atomically publishing their independent source scope."""
    return publish_metadata(db, prepare_dbt(request), actor)


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
