# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound a display projection while retaining the real members of action groups."""

from collections import deque
from typing import Literal

from datakeel.lineage.models import GraphEdge, GraphNode, GraphView

type EdgeKind = Literal["lineage", "semantic", "catalog"]
_KINDS: tuple[EdgeKind, ...] = ("lineage", "semantic", "catalog")


def _group(node: GraphNode) -> str:
    if node.asset_type == "action_run" and node.display_name:
        return f"action_run:{node.display_name}"
    return f"asset:{node.id}"


def _groups(view: GraphView) -> dict[str, list[GraphNode]]:
    result: dict[str, list[GraphNode]] = {}
    for node in view.nodes:
        result.setdefault(_group(node), []).append(node)
    return result


def _order(
    view: GraphView, groups: dict[str, list[GraphNode]], asset_id: str | None
) -> tuple[list[str], dict[str, EdgeKind]]:
    by_node = {node.id: _group(node) for node in view.nodes}
    adjacency: dict[str, list[tuple[str, EdgeKind]]] = {key: [] for key in groups}
    for edge in view.edges:
        source, target = by_node[edge.source], by_node[edge.target]
        adjacency[source].append((target, edge.kind))
        adjacency[target].append((source, edge.kind))
    root = by_node.get(asset_id or "")
    roots = ([root] if root else []) + sorted(key for key in groups if key != root)
    order: list[str] = []
    kinds: dict[str, EdgeKind] = {}
    for key in roots:
        if key in kinds:
            continue
        kinds[key] = "lineage"
        pending = deque([key])
        while pending:
            current = pending.popleft()
            order.append(current)
            for target, kind in sorted(
                adjacency[current], key=lambda item: (_KINDS.index(item[1]), item[0])
            ):
                if target not in kinds:
                    kinds[target] = kind
                    pending.append(target)
    return order, kinds


def _aggregate(kind: EdgeKind, count: int) -> GraphNode:
    identity = f"aggregate:{kind}:{count}"
    return GraphNode(
        id=identity,
        asset_id=identity,
        asset_type="aggregate",
        namespace="graph",
        label=identity,
        display_name=identity,
    )


def _edges(view: GraphView, replacements: dict[str, str]) -> list[GraphEdge]:
    result: list[GraphEdge] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for edge in view.edges:
        source, target = replacements[edge.source], replacements[edge.target]
        if source == target:
            continue
        key = (
            source,
            target,
            edge.kind,
            edge.assertion.id if edge.assertion else edge.event_id or "",
            edge.link_type or edge.operator,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(edge.model_copy(update={"source": source, "target": target}))
    return result


def collapse_graph(view: GraphView, asset_id: str | None, max_nodes: int) -> GraphView:
    """Limit display groups, assigning each hidden group to its first BFS edge kind.

    Action runs with the same display name remain separate response nodes so the
    frontend can inspect every real ID, but occupy one rendered archive card.
    Aggregate counts refer to hidden display groups, never guessed total counts.
    """
    groups = _groups(view)
    if len(groups) <= max_nodes:
        return view
    order, kinds = _order(view, groups, asset_id)
    keep = max_nodes
    while keep + len({kinds[key] for key in order[keep:]}) > max_nodes:
        keep -= 1
    visible = set(order[:keep])
    counts: dict[EdgeKind, int] = {
        kind: sum(kinds[key] == kind for key in order[keep:]) for kind in _KINDS
    }
    aggregates = {kind: _aggregate(kind, count) for kind, count in counts.items() if count}
    replacements = {
        node.id: node.id if key in visible else aggregates[kinds[key]].id
        for key, members in groups.items()
        for node in members
    }
    return view.model_copy(
        update={
            "nodes": [node for node in view.nodes if _group(node) in visible]
            + list(aggregates.values()),
            "edges": _edges(view, replacements),
            "truncated": True,
        }
    )
