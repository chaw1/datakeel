# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose deterministic associations and their review state over additive HTTP routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.storage.catalog_store import publish_snapshot
from tests.asgi_client import TestClient
from tests.storage.link_helpers import seed_link_graph, table_snapshot

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_association_routes_list_filter_and_rerun_current_links(db: Database) -> None:
    """Every route returns the same assertion IDs without duplicating link events."""
    seed_link_graph(db)
    publish_snapshot(db, table_snapshot())
    with TestClient(create_app(db)) as client:
        response = client.get("/api/kg/links?dataset_id=dataset&status=candidate")
        assert response.status_code == 200
        links = response.json()
        assert len(links) == 1
        entity_id = links[0]["entity"]["asset_ref"]["asset_id"]
        assert client.get(f"/api/kg/entities/{entity_id}/links").json() == links
        assert client.get("/api/kg/links?status=rejected").json() == []
        rerun = client.post("/api/kg/links/rerun")
        assert rerun.status_code == 200
        assert rerun.json() == {"entities": 2, "links": 1, "created": 0, "invalidated": 0}
