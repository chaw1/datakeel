# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Object discovery preserves public identity, context, exact lookup, and read-only behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions import service as actions
from datakeel.actions.models import ExecuteRequest
from datakeel.api.app import create_app
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.search_models import SEARCH_KINDS, SearchResult
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.dataset_service import DatasetInput, UploadFile, create_dataset, list_files
from datakeel.storage.events import all_events
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.fixture
def search_client(db: Database) -> TestClient:
    """Seed real dataset versions, a controlled run, and private catalog attributes."""
    dataset = create_dataset(
        db,
        DatasetInput(
            name="Generated archive",
            files=[UploadFile(filename="Résumé.txt", content_base64="bG9jYWw=")],
        ),
    )
    plan = actions.prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset.id}})
    )
    actions.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="generated",
            objects=tuple(
                CatalogObject(
                    asset_ref=AssetRef(asset_id=f"generated/{kind}", asset_type=kind),
                    name=f"Generated {kind}",
                    properties=JsonDocument({"private_connection": "never-disclose"}),
                )
                for kind in ("table", "column", "metric", "term")
            ),
        ),
    )
    return TestClient(create_app(db))


def test_search_when_empty_query_represents_all_eight_kinds_without_private_data(
    db: Database,
    search_client: TestClient,
) -> None:
    """A small initial palette has every kind and exposes no projection internals."""
    with db.session() as session:
        before = all_events(session)
    response = search_client.get("/api/search?limit=8")
    assert response.status_code == 200
    results = [SearchResult.model_validate(item) for item in response.json()]
    assert tuple(item.kind for item in results) == SEARCH_KINDS
    assert "never-disclose" not in response.text
    assert "object_key" not in response.text
    file = next(item for item in results if item.kind == "file")
    version = next(item for item in results if item.kind == "version")
    assert file.dataset_id == version.dataset_id
    assert file.version_id == version.id
    assert file.status == "quarantined"
    with db.session() as session:
        assert all_events(session) == before


def test_search_when_full_or_short_id_is_pasted_returns_exact_object_first(
    search_client: TestClient,
) -> None:
    """Every identity, including percent-encoded catalog identities, can be navigated."""
    results = search_client.get("/api/search?limit=100").json()
    for item in results:
        full = search_client.get("/api/search", params={"q": item["id"], "limit": 1}).json()
        assert full[0]["id"] == item["id"]
        if item["kind"] in {"dataset", "file", "version", "action_run"}:
            short = search_client.get(
                "/api/search", params={"q": item["id"][:8], "limit": 1}
            ).json()
            assert short[0]["id"] == item["id"]


def test_search_when_case_or_unicode_differs_matches_normalized_public_names(
    search_client: TestClient,
) -> None:
    """NFC/case normalization does not require callers to know a database spelling."""
    response = search_client.get("/api/search", params={"q": " RE\u0301SUME\u0301 "})
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Résumé.txt"
    assert search_client.get("/api/search?q=not-found").json() == []
    assert len(search_client.get("/api/search?q=generated&limit=2").json()) == 2


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "q=" + "x" * 201])
def test_search_when_request_exceeds_bounds_rejects(
    db: Database,
    query: str,
) -> None:
    """Discovery cannot silently lift its declared query and output bounds."""
    with TestClient(create_app(db)) as client:
        assert client.get(f"/api/search?{query}").status_code == 422
        assert client.post("/api/search", json={}).status_code == 405


def test_dataset_quality_when_requested_matches_quality_endpoint_without_changing_default(
    db: Database,
) -> None:
    """The optional summary uses the same measured latest manifest, with null for no files."""
    populated = create_dataset(
        db,
        DatasetInput(
            name="Generated low quality",
            files=[UploadFile(filename="empty.txt", content_base64="")],
        ),
    )
    empty = create_dataset(db, DatasetInput(name="Generated empty dataset"))
    assert len(list_files(db, populated.id)) == 1
    with TestClient(create_app(db)) as client:
        plain = client.get("/api/datasets").json()
        assert all("quality_score" not in item for item in plain)
        summaries = {
            item["id"]: item for item in client.get("/api/datasets?include=quality").json()
        }
        assert (
            summaries[populated.id]["quality_score"]
            == client.get(f"/api/datasets/{populated.id}/quality").json()["total"]
        )
        assert summaries[empty.id]["quality_score"] is None
        assert client.get("/api/datasets?include=secrets").status_code == 422
