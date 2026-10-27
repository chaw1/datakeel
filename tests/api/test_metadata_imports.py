# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP metadata imports only accept artifact contents and expose extended object kinds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_airflow_when_artifact_posted_exposes_dag_and_incremental_summary(db: Database) -> None:
    """Import content, browse its extended type, then retain source deletion as a tombstone."""
    client = TestClient(create_app(db))
    body = {"source_id": "scheduler", "document": {"dags": [{"dag_id": "daily_orders"}]}}
    first = client.post("/api/catalog/import/airflow", json=body)
    assert first.status_code == 200
    assert first.json()["new"] >= 1
    objects = client.get("/api/catalog/import/objects?kind=dag&source_id=scheduler&limit=1")
    assert objects.status_code == 200
    assert objects.json()["items"][0]["name"] == "daily_orders"
    second = client.post("/api/catalog/import/airflow", json=body)
    assert second.json()["unchanged"] == first.json()["object_count"]
    removed = client.post(
        "/api/catalog/import/airflow", json={"source_id": "scheduler", "document": {"dags": []}}
    )
    assert removed.json()["deleted"] >= 1
    tombstone = client.get("/api/catalog/import/objects?kind=dag").json()["items"][0]
    assert tombstone["properties"]["integration"]["source_deleted"] is True


def test_dbt_when_version_unknown_returns_explicit_validation_failure(db: Database) -> None:
    """Unsupported artifacts retain their actionable domain error at the HTTP boundary."""
    client = TestClient(create_app(db))
    response = client.post(
        "/api/catalog/import/dbt",
        json={
            "source_id": "shop",
            "manifest": {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v9.json"
                }
            },
        },
    )
    assert response.status_code == 422
    assert "version" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalog/import/objects?limit=1001",
        "/api/catalog/import/objects?offset=-1",
        "/api/catalog/import/objects?kind=unknown",
    ],
)
def test_import_objects_when_filter_invalid_rejects_request(db: Database, path: str) -> None:
    """New navigation retains bounded pagination and an explicit kind vocabulary."""
    assert TestClient(create_app(db)).get(path).status_code == 422


def test_import_when_server_path_supplied_rejects_unknown_field(db: Database) -> None:
    """An HTTP caller cannot ask the process to open an arbitrary server-side path."""
    response = TestClient(create_app(db)).post(
        "/api/catalog/import/dbt",
        json={"source_id": "shop", "manifest": {}, "path": "private.json"},
    )
    assert response.status_code == 422
