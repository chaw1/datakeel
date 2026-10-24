# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose bounded graph views and frozen source text through typed HTTP endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.core import predicate_registry
from tests.asgi_client import TestClient
from tests.kg.helpers import graph_product, seed_graph

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def test_kg_http_reads_include_reports_sources_and_missing_checks(db: Database) -> None:
    """Every new route returns typed local data without contacting any model."""
    product, source = graph_product(missing=True)
    assertions = seed_graph(db, product, source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    with TestClient(create_app(db)) as client:
        assert (
            client.post("/api/kg/query", json={}).json()["relations"][0]["assertion"]["id"]
            == relation.id
        )
        explanation = client.get(f"/api/kg/relations/{relation.id}").json()
        assert "tail entity could not be located" in explanation["summary"]
        assert client.post("/api/kg/graph", json={}).json()["nodes"]
        assert (
            client.get("/api/kg/sources/document?version_id=version").json()["text"] == source.text
        )
        assert client.get("/api/kg/sources/document").status_code == 422
        assert client.get("/api/kg/schemas").json()[0]["id"] == "business-knowledge"
        assert any(item["id"] == "replay-demo" for item in client.get("/api/kg/profiles").json())
        assert client.get("/api/kg/evaluations").json() == []
        assert (
            client.get("/api/kg/runs?dataset_id=dataset&version_id=version").json()[0]["id"]
            == "run-document"
        )
        assert client.get("/api/kg/runs/run-document/traces").json() == []
        assert client.get("/api/kg/runs/missing/traces").status_code == 404


def test_cold_non_graph_evidence_query_recovers_graph_vocabulary(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generic evidence reads remain available before any graph endpoint is opened."""
    product, source = graph_product()
    seed_graph(db, product, source)
    monkeypatch.setattr(
        predicate_registry,
        "_PREDICATES",
        {
            item.id: item
            for item in predicate_registry.registered_predicates()
            if not item.id.startswith("kg.")
        },
    )
    with TestClient(create_app(db)) as client:
        response = client.post("/api/evidence/query", json={})
    assert response.status_code == 200, response.text
    assert "kg.uses" in {item.id for item in predicate_registry.registered_predicates()}
