# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real review receipts remain in a file's bounded collapsed relation neighborhood."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.storage.evidence_queries import query_evidence
from tests.asgi_client import TestClient
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_graph_when_three_real_reviews_share_name_retains_all_action_run_ids(
    db: Database,
    tmp_path: Path,
) -> None:
    """Three decisions become inspectable members of one archive card without fake runs."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    sample = query_evidence(db, EvidenceQuery(dataset_id=dataset)).items[0]
    assertion = sample.assertions[0]
    with TestClient(create_app(db)) as client:
        run_ids = []
        for status in ("accepted", "rejected", "candidate"):
            response = client.post(
                "/api/evidence/assertions/decide",
                json={
                    "assertion_ids": [assertion.id],
                    "status": status,
                    "reason": "generated review",
                },
            )
            assert response.status_code == 200
            run_ids.append(response.json()["id"])
        params = {
            "asset_id": sample.asset_ref.asset_id,
            "hops": 2,
            "max_nodes": 25,
            "include_semantic": "true",
            "include_catalog": "true",
        }
        collapsed = client.get("/api/lineage/graph", params={**params, "collapse": "true"})
        assert collapsed.status_code == 200, collapsed.text
        nodes = collapsed.json()["nodes"]
        actions = [node for node in nodes if node["asset_type"] == "action_run"]
        assert {node["id"] for node in actions} == set(run_ids)
        assert {node["display_name"] for node in actions} == {"decide_assertions"}
        groups = {
            (
                node["asset_type"],
                node.get("display_name") if node["asset_type"] == "action_run" else node["id"],
            )
            for node in nodes
        }
        assert len(groups) <= 25
        legacy = client.get("/api/lineage/graph", params=params)
        assert len(legacy.json()["nodes"]) <= 25
        assert not any(node["asset_type"] == "aggregate" for node in legacy.json()["nodes"])
