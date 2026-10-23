# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Existing lineage HTTP queries expose optional bounded semantic evidence only."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.api.app import create_app
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.storage.database import EventRow
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import record_extraction
from datakeel.storage.lineage_service import export_events
from tests.asgi_client import TestClient
from tests.lineage.evidence_fixtures import extraction, pair

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_graph_endpoint_when_semantics_requested_keeps_legacy_projection_and_exports(
    db: Database,
) -> None:
    """Semantic edges are computed from assertions without writing lineage observations."""
    event = record_extraction(db, extraction((pair("a", "b"), pair("b", "c"))))
    bundle_id = event.outputs[0].asset_id
    before = export_events(db)
    with TestClient(create_app(db)) as client:
        legacy = client.get("/api/lineage/graph?asset=a&depth=1&direction=downstream").json()
        assert {node["id"] for node in legacy["nodes"]} == {"a", bundle_id}
        assert {edge["kind"] for edge in legacy["edges"]} == {"lineage"}
        response = client.get(
            "/api/lineage/graph?asset_id=c&include_semantic=true&hops=1&max_nodes=3"
        )
        assert response.status_code == 200
        graph = response.json()
        assert {node["id"] for node in graph["nodes"]} == {"b", "c", bundle_id}
        semantic = [edge for edge in graph["edges"] if edge["kind"] == "semantic"]
        assert [(edge["source"], edge["target"]) for edge in semantic] == [("b", "c")]
        assert semantic[0]["link_type"] == "similar_to"
        assert semantic[0]["assertion"]["extractor"]["id"] == "evidence.near_duplicate"
        assert "event" not in semantic[0]
        assert "event_id" not in semantic[0]
    assert export_events(db) == before
    with db.session() as session:
        assert len(list(session.scalars(select(EventRow)))) == 1


@pytest.mark.parametrize("state", ["accepted", "rejected", "invalidated"])
def test_graph_endpoint_when_assertion_state_changes_projects_only_usable_pairs(
    db: Database, state: str
) -> None:
    """Human review and extractor invalidation immediately change the disposable graph."""
    assertion = pair()
    record_extraction(db, extraction((assertion,)))
    if state == "invalidated":
        with db.session() as session:
            row = session.get(AssertionRow, assertion.id)
            assert row is not None
            row.active = False
            session.commit()
    else:
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(assertion.id,),
                status="accepted" if state == "accepted" else "rejected",
                actor="local",
                idempotency_key=f"review-{state}",
            ),
        )
    with TestClient(create_app(db)) as client:
        graph = client.get("/api/lineage/graph?include_semantic=true").json()
        semantic = [edge for edge in graph["edges"] if edge["kind"] == "semantic"]
        assert len(semantic) == (1 if state == "accepted" else 0)


@pytest.mark.parametrize(
    "query", ["hops=0", "hops=4", "max_nodes=0", "max_nodes=1001", "asset=a&asset_id=b"]
)
def test_graph_endpoint_when_bounds_invalid_returns_422(db: Database, query: str) -> None:
    """The existing route rejects invalid new bounds before evaluating the graph."""
    with TestClient(create_app(db)) as client:
        assert client.get(f"/api/lineage/graph?{query}").status_code == 422


def test_graph_endpoint_when_global_projection_large_defaults_to_200_nodes(db: Database) -> None:
    """Default browse is bounded even without an explicit focus or max_nodes parameter."""
    assertions = tuple(pair(f"a-{index:04d}", f"z-{index:04d}") for index in range(300))
    record_extraction(db, extraction(assertions))
    with TestClient(create_app(db)) as client:
        result = client.get("/api/lineage/graph").json()
        assert len(result["nodes"]) == 200
        assert result["truncated"] is True
        bounded = client.get("/api/lineage/graph?asset_id=z-0000&hops=1&max_nodes=1").json()
        assert [node["id"] for node in bounded["nodes"]] == ["z-0000"]
