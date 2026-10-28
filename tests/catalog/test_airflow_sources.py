# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Airflow datasets attach to the source that holds them, or to an explicit placeholder."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from datakeel.catalog.metadata_service import import_airflow
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.metadata_imports import AirflowImportRequest
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.orchestration_sources import source_namespace
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.catalog_store import publish_snapshot

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _object(kind: str, asset_id: str, properties: dict[str, Any]) -> CatalogObject:
    parts = asset_id.split("/")
    return CatalogObject(
        asset_ref=AssetRef(asset_type=kind, asset_id=asset_id, display_name=parts[-1]),
        name=parts[-1],
        source_id=parts[0],
        schema_name=parts[1] if len(parts) > 1 else None,
        properties=JsonDocument(properties),
    )


def _warehouse(db: Database) -> None:
    """A reflected server source whose connection names host, port and database."""
    url = "postgresql+pg8000://etl:secret@Warehouse.Example:5432/analytics"
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="source:warehouse",
            objects=(
                _object("source", "warehouse", {"connection_url": url, "dialect": "postgresql"}),
                _object("table", "warehouse/public/orders", {"columns": {"id": "INTEGER"}}),
            ),
        ),
    )


def _import(db: Database, *outlets: str) -> dict[str, CatalogObject]:
    document = {
        "dags": [{"dag_id": "nightly", "tasks": [{"task_id": "load", "outlets": list(outlets)}]}]
    }
    import_airflow(db, AirflowImportRequest(source_id="scheduler", document=JsonDocument(document)))
    with db.session() as session:
        return {item.asset_ref.asset_id: item for item in read_snapshot(session).objects}


def _details(item: CatalogObject) -> dict[str, Any]:
    integrations = item.properties.root.get("integrations")
    if isinstance(integrations, dict):
        return integrations["metadata:airflow:scheduler"]["details"]
    return item.properties.root["integration"]["details"]


def test_airflow_outlet_joins_the_source_whose_connection_names_the_same_database(
    db: Database,
) -> None:
    """Port, case and driver spellings normalize to the reflected table's one identity."""
    _warehouse(db)
    objects = _import(db, "postgres://warehouse.example:5432/analytics.public.orders")
    tables = [item for item in objects.values() if item.asset_ref.asset_type == "table"]
    assert [item.asset_ref.asset_id for item in tables] == ["warehouse/public/orders"]
    assert objects["warehouse/public/orders"].properties.root["columns"] == {"id": "INTEGER"}
    assert "unmatched_source" not in _details(objects["warehouse/public/orders"])
    assert "airflow" not in objects


def test_airflow_unmatched_datasets_are_filed_under_the_airflow_placeholder(
    db: Database,
) -> None:
    """Other servers, databases and object stores stay apart and are marked unmatched."""
    _warehouse(db)
    objects = _import(
        db,
        "postgres://ehr-db.example/ehr.public.orders",
        "postgres://warehouse.example/billing.public.orders",
        "s3://clinic-exports/daily/visits.v2.parquet",
    )
    placeholders = {
        item.asset_ref.asset_id
        for item in objects.values()
        if item.asset_ref.asset_type == "table" and item.source_id == "airflow"
    }
    assert placeholders == {
        catalog_id("airflow", "postgres://ehr-db.example/ehr.public", "orders"),
        catalog_id("airflow", "postgres://warehouse.example/billing.public", "orders"),
        catalog_id("airflow", "s3://clinic-exports", "daily/visits.v2.parquet"),
    }
    assert all(_details(objects[identity])["unmatched_source"] is True for identity in placeholders)
    assert objects["airflow"].asset_ref.asset_type == "source"
    assert objects["airflow"].name == "airflow"
    assert "scheduler/public/orders" not in objects


def test_airflow_explicit_namespace_mapping_attaches_datasets_to_a_dbt_source(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sources without a server URL (dbt, SQLite) are matched through explicit mappings."""
    mapping = {"duckdb://warehouse": {"source_id": "clinic", "database": "clinic"}}
    monkeypatch.setenv("DATAKEEL_OPENLINEAGE_NAMESPACES", json.dumps(mapping))
    objects = _import(db, "duckdb://warehouse/clinic.main.fct_visits")
    assert "clinic/main/fct_visits" in objects
    assert "unmatched_source" not in _details(objects["clinic/main/fct_visits"])


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:////srv/warehouse.sqlite",
        "postgresql://warehouse.example",
        "postgresql://warehouse.example:notaport/analytics",
    ],
)
def test_source_namespace_requires_a_server_and_a_database(url: str) -> None:
    """File databases and server-level connections cannot prove which dataset they hold."""
    assert source_namespace("warehouse", url) is None
