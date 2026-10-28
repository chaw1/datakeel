# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP version ownership, draft generation, cited downloads and publication approval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.storage.dataset_service import import_paths, list_versions
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_http_datasheet_generate_download_publish_and_compare(db: Database, tmp_path: Path) -> None:
    """Every browser operation reaches the real versioned store and controlled action gate."""
    path = tmp_path / "generated.txt"
    path.write_text("Generated local dataset documentation fixture.")
    dataset = import_paths(db, "Fixture Dataset", [path])
    version = list_versions(db, dataset.id)[0]
    with TestClient(create_app(db)) as client:
        plan = client.post(
            f"/api/datasets/{dataset.id}/datasheets",
            json={"version_id": version.id},
        )
        assert plan.status_code == 200, plan.text
        generated = client.post(
            f"/api/actions/{plan.json()['id']}/execute",
            json={"plan_digest": plan.json()["plan_digest"]},
        )
        assert generated.status_code == 200, generated.text
        documents = client.get(f"/api/datasets/{dataset.id}/datasheets").json()
        assert len(documents) == 1
        document = documents[0]
        assert client.get(f"/api/datasheets/{document['id']}").json() == document
        for output_format in ("markdown", "html"):
            downloaded = client.get(
                f"/api/datasheets/{document['id']}/download",
                params={"format": output_format},
            )
            assert downloaded.status_code == 200
            assert "attachment" in downloaded.headers["content-disposition"]
            assert document["facts"][0]["id"] in downloaded.text
            assert "平台中没有这一项的记录" in downloaded.text
        comparison = client.get(f"/api/datasheets/{document['id']}/compare/{document['id']}")
        assert comparison.status_code == 200
        assert comparison.json()["changes"] == []
        publication = client.post(f"/api/datasheets/{document['id']}/publish").json()
        denied = client.post(
            f"/api/actions/{publication['id']}/execute",
            json={"plan_digest": publication["plan_digest"]},
        )
        assert denied.status_code == 403
        assert client.get("/api/datasheets/missing").status_code == 404
        assert client.get("/api/datasheets/jobs/missing").status_code == 404


def test_http_datasheet_rejects_another_datasets_version(db: Database, tmp_path: Path) -> None:
    """Version IDs from other datasets cannot authorize fact extraction or model outbound data."""
    path = tmp_path / "fixture.txt"
    path.write_text("Generated version ownership fixture.")
    left = import_paths(db, "Left Fixture", [path])
    right = import_paths(db, "Right Fixture", [path])
    version = list_versions(db, right.id)[0]
    with TestClient(create_app(db)) as client:
        response = client.post(
            f"/api/datasets/{left.id}/datasheets",
            json={"version_id": version.id},
        )
        assert response.status_code == 404
        assert client.get(f"/api/datasets/{left.id}/datasheets").json() == []
