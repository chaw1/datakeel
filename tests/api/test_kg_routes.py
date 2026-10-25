# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose bounded graph views and frozen source text through typed HTTP endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.core import predicate_registry
from datakeel.kg.loader import contracts_path
from datakeel.storage.dataset_service import import_paths, list_versions
from tests.asgi_client import TestClient
from tests.kg.helpers import graph_product, seed_graph
from tests.worker.image_helpers import image_dataset

if TYPE_CHECKING:
    from pathlib import Path

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


def test_transcription_profiles_hide_scripted_backends_and_failures(db: Database) -> None:
    """Only usable configurations are advertised, while packaged demo replay remains selectable."""
    with TestClient(create_app(db)) as client:
        profiles = client.get("/api/kg/transcription-profiles").json()
    assert any(profile["id"] == "replay-image-demo" for profile in profiles)
    assert all(profile["backend"] != "fake" for profile in profiles)
    assert all(not profile["id"].endswith("-failure") for profile in profiles)


def test_image_openapi_documents_png_and_expected_failures(db: Database) -> None:
    """Binary PNG success and domain/validation failures are visible to generated clients."""
    with TestClient(create_app(db)) as client:
        schema = client.get("/api/openapi.json").json()
        responses = schema["paths"]["/api/kg/images/{file_id}"]["get"]["responses"]
        assert set(responses["200"]["content"]) == {"image/png"}
        assert {"404", "422"} <= responses.keys()
        assert client.get("/api/kg/images/missing").status_code == 422
        assert (
            client.get("/api/kg/images/missing?version_id=v&extraction_id=missing").status_code
            == 404
        )


def test_transcription_default_requires_complete_recording_coverage(
    db: Database, tmp_path: Path
) -> None:
    """One unknown image prevents the demo default; text files neither require nor block it."""
    generated = image_dataset(db, tmp_path)
    text = tmp_path / "document.txt"
    text.write_text("Acme uses Widget.", encoding="utf-8")
    recorded = contracts_path() / "eval/image/images/en01_clean.png"
    choices = (
        ("Recorded and text", [recorded, text], "replay-image-demo", 1),
        ("Mixed known and unknown", [recorded, tmp_path / "image-0.png"], None, 2),
        ("Text only", [text], None, 0),
    )
    with TestClient(create_app(db)) as client:
        unknown = client.get(
            "/api/kg/transcription-selection",
            params={
                "dataset_id": generated.dataset_id,
                "version_id": generated.version_id,
            },
        )
        assert unknown.json() == {"image_count": 1, "default_profile_id": None}
        for name, paths, default, count in choices:
            dataset = import_paths(db, name, paths)
            version = list_versions(db, dataset.id)[0]
            response = client.get(
                "/api/kg/transcription-selection",
                params={
                    "dataset_id": dataset.id,
                    "version_id": version.id,
                },
            )
            assert response.status_code == 200
            assert response.json() == {"image_count": count, "default_profile_id": default}
        assert (
            client.get(
                "/api/kg/transcription-selection",
                params={
                    "dataset_id": generated.dataset_id,
                    "version_id": "missing",
                },
            ).status_code
            == 404
        )
