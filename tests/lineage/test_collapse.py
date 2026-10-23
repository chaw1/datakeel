# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Collapsed graphs count real hidden display groups and retain inspectable run members."""

import pytest
from pydantic import ValidationError

from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.collapse import collapse_graph
from datakeel.lineage.models import GraphEdge, GraphNode, GraphQuery, GraphView
from datakeel.lineage.service import graph
from tests.lineage.evidence_fixtures import pair


def _node(identity: str) -> GraphNode:
    return GraphNode(
        id=identity, asset_id=identity, asset_type="file", namespace="default", label=identity
    )


def _mixed_graph() -> GraphView:
    event = LineageEvent(
        event_id="generated-event", idempotency_key="generated-event", operator="generated"
    )
    nodes = [_node("root")]
    edges: list[GraphEdge] = []
    for index in range(30):
        for kind in ("lineage", "semantic", "catalog"):
            identity = f"{kind}-{index:02d}"
            nodes.append(_node(identity))
            edges.append(
                GraphEdge(
                    source="root",
                    target=identity,
                    kind=kind,
                    operator="generated",
                    event_id=None if kind == "semantic" else event.event_id,
                    assertion=pair("root", identity) if kind == "semantic" else None,
                    link_type="similar_to"
                    if kind == "semantic"
                    else "references"
                    if kind == "catalog"
                    else None,
                )
            )
    return GraphView(nodes=nodes, edges=edges, events=[event])


def test_collapse_when_three_edge_kinds_overflow_preserves_exact_partition_and_node_budget() -> (
    None
):
    """Every omitted real node is counted once and aggregates consume visible slots."""
    full = _mixed_graph()
    result = collapse_graph(full, "root", 25)
    assert result.truncated
    assert len(result.nodes) == 25
    assert "root" in {node.id for node in result.nodes}
    aggregates = {
        node.id.split(":")[1]: int(node.id.split(":")[2])
        for node in result.nodes
        if node.asset_type == "aggregate"
    }
    assert set(aggregates) == {"lineage", "semantic", "catalog"}
    for kind, count in aggregates.items():
        assert count + sum(node.id.startswith(f"{kind}-") for node in result.nodes) == 30
    assert all(
        edge.source in {node.id for node in result.nodes}
        and edge.target in {node.id for node in result.nodes}
        for edge in result.edges
    )
    assert result.events == full.events
    assert all(
        edge.assertion is not None
        if edge.kind == "semantic"
        else edge.event_id == "generated-event"
        for edge in result.edges
    )


def test_collapse_when_runs_share_name_counts_one_display_card_but_retains_every_id() -> None:
    """The opt-in capacity is rendered cards, preserving raw run IDs for hover and expansion."""
    event = LineageEvent(
        idempotency_key="generated-runs",
        operator="decide_assertions",
        inputs=[AssetRef(asset_type="file", asset_id="root")],
        outputs=[
            AssetRef(
                asset_type="action_run", asset_id=f"run-{index}", display_name="decide_assertions"
            )
            for index in range(40)
        ],
    )
    full = graph([event], "root", depth=1)
    result = collapse_graph(full, "root", 4)
    assert result == full
    assert len(result.nodes) == 41
    assert (
        len(
            {
                (node.asset_type, node.display_name if node.asset_type == "action_run" else node.id)
                for node in result.nodes
            }
        )
        == 2
    )
    assert len(graph([event], "root", depth=1, max_nodes=4).nodes) == 4


def test_collapse_when_group_hidden_counts_one_group_not_each_action_member() -> None:
    """A grouped run represents one omitted card even when several receipts back it."""
    full = _mixed_graph()
    members = [
        _node(f"run-{index}").model_copy(
            update={"asset_type": "action_run", "display_name": "same"}
        )
        for index in range(3)
    ]
    view = full.model_copy(update={"nodes": full.nodes + members})
    result = collapse_graph(view, "root", 4)
    assert len(result.nodes) == 4
    assert (
        sum(int(node.id.split(":")[2]) for node in result.nodes if node.asset_type == "aggregate")
        == 91
    )


def test_collapse_when_input_order_changes_is_deterministic_in_selected_members() -> None:
    """The same root and complete neighborhood select the same groups independent of enumeration."""
    full = _mixed_graph()
    reverse = full.model_copy(
        update={"nodes": list(reversed(full.nodes)), "edges": list(reversed(full.edges))}
    )
    first, second = collapse_graph(full, "root", 25), collapse_graph(reverse, "root", 25)
    assert {node.id for node in first.nodes} == {node.id for node in second.nodes}
    assert len(collapse_graph(full, None, 4).nodes) == 4


def test_collapsed_query_when_capacity_too_small_rejects_without_changing_legacy_limits() -> None:
    """The new mode reserves room for the root and up to three kind-specific aggregates."""
    with pytest.raises(ValidationError, match="three edge-kind"):
        GraphQuery(collapse=True, max_nodes=3)
    assert GraphQuery(max_nodes=1).max_nodes == 1
