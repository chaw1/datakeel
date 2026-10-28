# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph run reports and lineage nodes must not disclose protected extracted names."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.models import AssetRef
from datakeel.storage.database import Database
from tests.assets.entry_helpers import grant, publish, seed_resources
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)


def _client(db: Database) -> TestClient:
    return TestClient(create_app(db), headers={"X-Datakeel-Actor": "reader"})


def test_graph_runs_and_lineage_when_protected_hide_extracted_names(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run reports and lineage nodes quote extracted entities until the reader is granted."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_graph(db, dataset))
    asset = publish(db, AssetRef(asset_id=dataset.dataset_id))
    lineage = {"asset_id": dataset.dataset_id}
    with _client(db) as client:
        assert run.id not in client.get("/api/kg/runs").text
        assert client.get("/api/kg/runs", params={"dataset_id": dataset.dataset_id}).json() == []
        denied = client.get("/api/lineage/graph", params=lineage)
        assert denied.status_code == 403
        assert "apply for access" in denied.text
        assert "Widget" not in denied.text
    grant(db, asset, "valid", "query", subject="reader")
    with _client(db) as client:
        assert [item["id"] for item in client.get("/api/kg/runs").json()] == [run.id]
        allowed = client.get("/api/lineage/graph", params=lineage)
        assert allowed.status_code == 200
        assert "Widget" in allowed.text


def test_catalog_lineage_of_protected_metric_stays_visible(db: Database, tmp_path: Path) -> None:
    """Metadata-only lineage matches the public asset card and needs no grant."""
    seed_resources(db, tmp_path)
    publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    with _client(db) as client:
        response = client.get(
            "/api/lineage/graph",
            params={"asset_id": "retail_revenue", "include_catalog": "true", "hops": 2},
        )
    assert response.status_code == 200
    assert any(node["asset_type"] == "table" for node in response.json()["nodes"])
