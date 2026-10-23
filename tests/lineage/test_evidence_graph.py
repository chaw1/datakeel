# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic neighbors are bounded, deterministic, and never transitively inferred."""

import pytest
from pydantic import ValidationError

from datakeel.core.evidence_models import EvidenceValue
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.models import GraphEdge, GraphQuery
from datakeel.lineage.service import graph
from tests.lineage.evidence_fixtures import extraction, pair


def test_graph_when_semantic_pairs_form_chain_traverses_both_ways_without_closure() -> None:
    """A canonical pair is reachable from its target without creating reverse or A-C edges."""
    pairs = (pair("a", "b"), pair("b", "c"))
    first = graph([], "c", "downstream", 1, pairs)
    assert {node.id for node in first.nodes} == {"b", "c"}
    full = graph([], "c", "upstream", 2, pairs)
    assert {(edge.source, edge.target) for edge in full.edges} == {("a", "b"), ("b", "c")}
    assert all(edge.kind == "semantic" and edge.event is None for edge in full.edges)
    assert all(edge.link_type == "similar_to" for edge in full.edges)
    assert full.events == []


def test_graph_when_node_limit_reached_selects_breadth_first_sorted_asset_id() -> None:
    """Input enumeration cannot change which same-depth neighbors survive truncation."""
    pairs = (pair("a", "z"), pair("b", "z"), pair("c", "z"), pair("a", "d"))
    first = graph([], "z", "both", 3, pairs, 3)
    shuffled = graph([], "z", "both", 3, tuple(reversed(pairs)), 3)
    assert [node.id for node in first.nodes] == ["a", "b", "z"]
    assert first == shuffled
    assert first.truncated
    assert len(graph([], "z", "both", 1, pairs, 1).nodes) == 1


def test_graph_when_neighbor_types_differ_sorts_type_before_identifier() -> None:
    """A lexically later artifact precedes a file at the same BFS distance."""
    event = LineageEvent(
        idempotency_key="typed-neighbors",
        operator="fixture",
        inputs=[AssetRef(asset_id="root")],
        outputs=[
            AssetRef(asset_type="file", asset_id="a"),
            AssetRef(asset_type="artifact", asset_id="z"),
        ],
    )
    result = graph([event], "root", depth=1, max_nodes=2)
    assert [node.id for node in result.nodes] == ["z", "root"]
    assert result.truncated


def test_graph_when_global_projection_has_disconnected_nodes_still_obeys_limit() -> None:
    """Global browse uses a stable BFS forest and limits disconnected components too."""
    result = graph([], assertions=(pair("a", "b"), pair("c", "d")), max_nodes=2)
    assert [node.id for node in result.nodes] == ["a", "b"]
    assert result.truncated


def test_graph_when_assertions_rejected_or_unary_does_not_project_semantic_edges() -> None:
    """Only usable binary near-duplicate evidence becomes a similar_to edge."""
    rejected = pair().model_copy(update={"status": "rejected"})
    mention = pair().model_copy(
        update={"predicate": "mentions", "object": EvidenceValue(concept="person", value="present")}
    )
    assert graph([], assertions=(rejected, mention)).edges == []


def test_graph_when_big_bundle_is_bounded_keeps_complete_event_only_once() -> None:
    """A thousand-input bundle cannot repeat its full input list on each visible edge."""
    event = extraction((pair(),)).model_copy(
        update={
            "inputs": [AssetRef(asset_type="file", asset_id=f"sample-{i:04d}") for i in range(1000)]
        }
    )
    result = graph([event], "bundle", max_nodes=200)
    assert len(result.nodes) == 200
    assert result.truncated
    assert all(edge.event is None for edge in result.edges)
    assert result.events == [event]
    assert len(result.model_dump_json()) < 400_000
    assert len(graph([event]).nodes) == 1001


def test_graph_when_failed_event_declares_outputs_never_derives_an_edge() -> None:
    """Malformed failure output claims cannot masquerade as completed transformations."""
    event = extraction((pair(),)).model_copy(update={"run_state": "FAIL"})
    result = graph([event], "a")
    assert result.edges == []
    assert result.events == [event]


def test_graph_when_lineage_and_semantics_share_assets_keeps_independent_backing() -> None:
    """The extraction is lineage; the resulting pair remains a separate semantic fact."""
    assertion = pair()
    event = extraction((assertion,))
    result = graph([event], "a", assertions=(assertion,))
    assert {edge.kind for edge in result.edges} == {"lineage", "semantic"}
    assert len(result.events) == 1
    semantic = next(edge for edge in result.edges if edge.kind == "semantic")
    assert semantic.assertion == assertion
    assert semantic.event_id is None


@pytest.mark.parametrize("parameters", [{"hops": 0}, {"hops": 4}, {"max_nodes": 0}])
def test_graph_query_when_bounds_invalid_rejects_request(parameters: dict[str, int]) -> None:
    """Invalid traversal bounds are rejected at the pydantic boundary."""
    with pytest.raises(ValidationError):
        GraphQuery.model_validate(parameters)


def test_graph_query_when_focus_aliases_conflict_rejects_request() -> None:
    """Two focus spellings must never select an ambiguous asset."""
    with pytest.raises(ValidationError, match="same asset"):
        GraphQuery(asset="a", asset_id="b")


def test_graph_edge_when_semantic_claims_event_provenance_is_invalid() -> None:
    """Semantic evidence cannot be serialized as an event-derived transformation."""
    assertion = pair()
    with pytest.raises(ValidationError, match="distinguish"):
        GraphEdge(
            source="a",
            target="b",
            kind="semantic",
            operator="similar_to",
            assertion=assertion,
            link_type="similar_to",
            event_id="near-event",
        )
