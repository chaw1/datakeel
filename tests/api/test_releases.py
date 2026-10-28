# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publication HTTP reads preserve exact ownership, bounded pages, and immutable facts."""

from pathlib import Path

from datakeel.api.app import create_app
from datakeel.storage.database import Database
from tests.asgi_client import TestClient
from tests.storage.test_releases import published_fixture


def test_release_and_diff_http_reads_are_paged_and_read_only(db: Database, tmp_path: Path) -> None:
    """Expose the approved snapshot, compare legacy versions, and reject public mutation verbs."""
    dataset, version, identifier = published_fixture(db, tmp_path)
    with TestClient(create_app(db)) as client:
        listed = client.get(f"/api/datasets/{dataset}/releases")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == identifier
        detail = client.get(f"/api/releases/{identifier}")
        assert detail.status_code == 200
        assert detail.json()["metadata"] == {"purpose": "example"}
        page = client.get(f"/api/releases/{identifier}/files", params={"limit": 1})
        assert page.status_code == 200
        assert page.json()["files"][0]["source_version"] == version
        diff = client.get(
            f"/api/datasets/{dataset}/diff",
            params={"before": version, "after": version, "limit": 1, "category": "unchanged"},
        )
        assert diff.status_code == 200, diff.text
        assert diff.json()["counts"]["unchanged"] == 1
        assert (
            client.patch(f"/api/releases/{identifier}", json={"notes": "changed"}).status_code
            == 405
        )
        assert (
            client.patch(f"/api/releases/{identifier}/files", json={"files": []}).status_code == 405
        )
        assert (
            client.get(
                f"/api/datasets/{dataset}/diff",
                params={"before": version, "after": version, "limit": 1001},
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/datasets/other/diff", params={"before": version, "after": version}
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/releases/{identifier}/files", params={"offset": -1}).status_code
            == 422
        )
