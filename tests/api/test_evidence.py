# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence HTTP contracts preserve provenance, pagination, and controlled decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ActionRun
from datakeel.api.app import create_app
from datakeel.evidence.query_models import EvidenceQueryResult, EvidenceSample
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_store import list_assertions
from tests.asgi_client import TestClient
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_query_when_paginated_returns_versioned_typed_samples_in_asset_order(
    db: Database, tmp_path: Path
) -> None:
    """Pages retain complete selectors, measured quality, and immutable source identity."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    with TestClient(create_app(db)) as client:
        request = {"dataset_id": dataset, "split": "val", "page_size": 2}
        first_response = client.post("/api/evidence/query", json=request)
        assert first_response.status_code == 200, first_response.text
        first = EvidenceQueryResult.model_validate(first_response.json())
        assert first.total == 4
        assert len(first.items) == 2
        assert first.next_cursor == first.items[-1].asset_ref.asset_id
        second = EvidenceQueryResult.model_validate(
            client.post("/api/evidence/query", json={**request, "cursor": first.next_cursor}).json()
        )
        items = first.items + second.items
        ids = [item.asset_ref.asset_id for item in items]
        assert ids == sorted(set(ids))
        assert len(ids) == 4
        assert second.next_cursor is None
        assert all(item.split == "val" and 0 <= item.quality_score <= 100 for item in items)
        assert all(item.source_version == item.asset_ref.version for item in items)
        assert all(item.assertions for item in items)
        assert all(
            assertion.anchors and assertion.extractor.version and assertion.producer_event_id
            for item in items
            for assertion in item.assertions
        )
        detail = client.get(f"/api/evidence/assets/{ids[0]}")
        assert detail.status_code == 200
        assert EvidenceSample.model_validate(detail.json()).asset_ref == first.items[0].asset_ref


def test_thumbnail_when_returned_uses_owned_object_download_without_paths(
    db: Database, tmp_path: Path
) -> None:
    """Only declared dataset/file identities resolve local images; corrupt previews are absent."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    with TestClient(create_app(db)) as client:
        response = client.post("/api/evidence/query", json={"dataset_id": dataset})
        items = EvidenceQueryResult.model_validate(response.json()).items
        readable = next(item for item in items if item.thumbnail_url is not None)
        assert readable.thumbnail_url is not None
        assert readable.thumbnail_url.startswith(f"/api/datasets/{dataset}/files/")
        image = client.get(readable.thumbnail_url)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
        corrupt = next(item for item in items if "scene-0019" in item.filename)
        assert corrupt.thumbnail_url is None
        assert str(tmp_path) not in response.text
        assert "object_key" not in response.text
        other = client.post(
            "/api/datasets",
            json={
                "name": "unrelated dataset",
                "files": [{"filename": "local.txt", "content_base64": "bG9jYWw="}],
            },
        )
        assert other.status_code == 201
        cross_dataset = client.get(
            f"/api/datasets/{other.json()['id']}/files/{readable.asset_ref.asset_id}/download"
        )
        assert cross_dataset.status_code == 404
        assert (
            client.get(
                f"/api/datasets/unknown/files/{readable.asset_ref.asset_id}/download"
            ).status_code
            == 404
        )
        assert client.get(f"/api/datasets/{dataset}/files/unknown/download").status_code == 404


def test_decision_when_reversed_appends_audit_and_retains_extracted_content(
    db: Database, tmp_path: Path
) -> None:
    """The convenience endpoint uses Action plans and supports reject then restore."""
    seed_query_evidence(db, tmp_path / "samples")
    assertion = next(item for item in list_assertions(db) if item.predicate == "mentions")
    with TestClient(create_app(db)) as client:
        for status in ("rejected", "accepted", "candidate"):
            response = client.post(
                "/api/evidence/assertions/decide",
                json={"assertion_ids": [assertion.id], "status": status, "reason": "review"},
            )
            assert response.status_code == 200, response.text
            run = ActionRun.model_validate(response.json())
            assert run.status == "SUCCEEDED"
            assert run.action_type == "decide_assertions"
            assert run.receipt is not None
            detail = EvidenceSample.model_validate(
                client.get(f"/api/evidence/assets/{assertion.subject.asset_id}").json()
            )
            updated = next(item for item in detail.assertions if item.id == assertion.id)
            assert updated.status == status
            assert updated.decided_by == "local"
            assert updated.anchors == assertion.anchors
            assert updated.producer_event_id == assertion.producer_event_id
    decisions = list_decisions(db, assertion.id)
    assert [item.status for item in decisions] == ["rejected", "accepted", "candidate"]
    assert all(item.actor == "local" for item in decisions)


@pytest.mark.parametrize("body", [{"page_size": 0}, {"schema_version": "9"}, {"actor": "admin"}])
def test_query_when_boundary_invalid_rejects_undeclared_or_unbounded_parameters(
    db: Database, body: dict[str, str | int]
) -> None:
    """Requests cannot weaken the declared ObjectSet and page boundary."""
    with TestClient(create_app(db)) as client:
        assert client.post("/api/evidence/query", json=body).status_code == 422
        assert client.get("/api/evidence/assets/missing").status_code == 404


def test_decision_when_actor_or_content_injected_rejects_without_mutation(db: Database) -> None:
    """HTTP callers can choose a review state but cannot supply identities or new facts."""
    with TestClient(create_app(db)) as client:
        for extra in ({"actor": "admin"}, {"predicate": "corrupt"}):
            response = client.post(
                "/api/evidence/assertions/decide",
                json={"assertion_ids": ["missing"], "status": "accepted", **extra},
            )
            assert response.status_code == 422
        assert list_decisions(db) == []


def test_query_schema_when_advertised_only_accepts_file_objects(db: Database) -> None:
    """OpenAPI does not promise object kinds the evidence validator cannot serve."""
    with TestClient(create_app(db)) as client:
        schema = client.get("/api/openapi.json").json()["components"]["schemas"]["EvidenceQuery"]
        assert schema["properties"]["object_type"]["enum"] == ["file"]
        for object_type in ("dataset", "version", "artifact", "task"):
            response = client.post("/api/evidence/query", json={"object_type": object_type})
            assert response.status_code == 422


def test_query_when_concept_filter_selected_returns_matching_assertions(
    db: Database, tmp_path: Path
) -> None:
    """The wire body accepts ObjectSet 1.1 predicate and canonical concept filters."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    version, _ = source_manifest(db, dataset)
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/evidence/query",
            json={
                "schema_version": "1.1",
                "dataset_id": dataset,
                "version_ids": [version],
                "assertion_filters": [
                    {"predicate": "mentions", "concept": "person", "value": "present"}
                ],
            },
        )
        assert response.status_code == 200, response.text
        result = EvidenceQueryResult.model_validate(response.json())
        assert result.items
        assert all(
            any(
                assertion.predicate == "mentions"
                and assertion.object.model_dump().get("concept") == "person"
                for assertion in item.assertions
            )
            for item in result.items
        )
