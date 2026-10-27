# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Idempotent append-only events and rebuildable graph projections."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import networkx as nx

from datakeel.core.catalog_projection import CATALOG_OPERATORS
from datakeel.core.models import AssetRef
from datakeel.lineage.models import GraphEdge, GraphNode, GraphOverlay, GraphView
from datakeel.storage.events import all_events, append_event

if TYPE_CHECKING:
    from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
    from datakeel.core.evidence_models import Assertion
    from datakeel.core.models import LineageEvent

type Projection = nx.MultiDiGraph[str, dict[str, Any], dict[str, Any]]
INLINE_EVENT_REFS = 32


def _add_asset(projection: Projection, ref: AssetRef) -> None:
    previous = projection.nodes[ref.asset_id] if ref.asset_id in projection else {}
    values = {**previous, **{k: v for k, v in ref.model_dump().items() if v is not None}}
    values["label"] = ref.display_name or previous.get("label", ref.asset_id)
    projection.add_node(ref.asset_id, **values)


def _project_events(projection: Projection, events: list[LineageEvent]) -> None:
    for event in events:
        if event.operator in CATALOG_OPERATORS and "catalog_snapshot" in event.params:
            continue
        for ref in event.inputs + event.outputs:
            _add_asset(projection, ref)
        if event.run_state in {"FAIL", "FAILED", "ABORT"}:
            continue
        # Keep large bundle events once in GraphView.events rather than on every edge.
        inline = len(event.inputs) + len(event.outputs) <= INLINE_EVENT_REFS
        for source in event.inputs:
            for target in event.outputs:
                projection.add_edge(
                    source.asset_id,
                    target.asset_id,
                    key=event.event_id,
                    kind="lineage",
                    event_id=event.event_id,
                    operator=event.operator,
                    event=event.model_dump(mode="json") if inline else None,
                )


def _project_catalog(
    projection: Projection, events: list[LineageEvent], snapshot: CatalogSnapshot
) -> None:
    by_id = {event.event_id: event for event in events}
    for link in snapshot.links:
        event = by_id.get(link.producer_event_id or "")
        if event is not None:
            _add_asset(projection, link.source)
            _add_asset(projection, link.target)
            projection.add_edge(
                link.source.asset_id,
                link.target.asset_id,
                key=f"{event.event_id}:{link.kind}",
                kind="catalog",
                event_id=event.event_id,
                operator=event.operator,
                link_type=link.kind,
            )
    names = {item.asset_ref.asset_id: item.name for item in snapshot.objects}
    for item in snapshot.objects:
        _add_asset(
            projection,
            item.asset_ref.model_copy(update={"display_name": _catalog_name(item, names)}),
        )


def _catalog_name(item: CatalogObject, names: dict[str, str]) -> str:
    if item.asset_ref.asset_type == "column" and item.table_id:
        table_name = names.get(item.table_id, item.table_id.rsplit("/", 1)[-1])
        return f"{table_name}.{item.name}"
    return item.name


def _project_semantics(projection: Projection, assertions: tuple[Assertion, ...]) -> None:
    for assertion in assertions:
        if (
            assertion.predicate != "near_duplicate_of"
            or assertion.status == "rejected"
            or not isinstance(assertion.object, AssetRef)
        ):
            continue
        _add_asset(projection, assertion.subject)
        _add_asset(projection, assertion.object)
        projection.add_edge(
            assertion.subject.asset_id,
            assertion.object.asset_id,
            key=f"assertion:{assertion.id}",
            kind="semantic",
            operator="similar_to",
            link_type="similar_to",
            assertion=assertion.model_dump(mode="json"),
        )


def graph(
    events: list[LineageEvent],
    asset: str | None = None,
    direction: str = "both",
    depth: int = 20,
    assertions: tuple[Assertion, ...] | GraphOverlay = (),
    max_nodes: int | None = None,
) -> GraphView:
    """Project directed lineage and symmetric semantics without persisting derived edges.

    Legacy internal export callers remain unbounded by node count; API callers supply
    max_nodes. Semantic pairs are traversable from either endpoint but emitted once.
    Catalog-focused queries traverse explicit metadata relationships; action receipts
    and answer bundles remain available through their own event or asset views.
    """
    projection: Projection = nx.MultiDiGraph()
    overlay = (
        assertions if isinstance(assertions, GraphOverlay) else GraphOverlay(assertions=assertions)
    )
    catalog_focus = overlay.catalog is not None and any(
        item.asset_ref.asset_id == asset for item in overlay.catalog.objects
    )
    if not catalog_focus:
        _project_events(projection, events)
    if overlay.catalog is not None:
        _project_catalog(projection, events, overlay.catalog)
    _project_semantics(projection, overlay.assertions)
    selected, truncated = _neighbors(projection, asset, direction, depth, max_nodes)
    edges = [
        GraphEdge.model_validate({"source": u, "target": v, **data})
        for u, v, data in projection.edges(data=True)
        if u in selected and v in selected
    ]
    edges.sort(
        key=lambda edge: (
            edge.source,
            edge.target,
            edge.kind,
            edge.assertion.id if edge.assertion is not None else edge.event_id or "",
        )
    )
    event_ids = {edge.event_id for edge in edges if edge.event_id is not None}
    return GraphView(
        nodes=[
            GraphNode.model_validate({"id": node, **projection.nodes[node]})
            for node in sorted(selected, key=lambda node: _sort_key(projection, node))
        ],
        edges=edges,
        events=_visible_events(events, event_ids, selected, asset),
        truncated=truncated,
    )


def _visible_events(
    events: list[LineageEvent], event_ids: set[str], selected: set[str], asset: str | None
) -> list[LineageEvent]:
    result: list[LineageEvent] = []
    for event in events:
        if event.operator in CATALOG_OPERATORS and not any(
            ref.asset_id in selected for ref in event.outputs
        ):
            continue
        edgeless = (
            not event.inputs or not event.outputs or event.run_state in {"FAIL", "FAILED", "ABORT"}
        )
        incident = not asset or any(
            ref.asset_id in selected for ref in event.inputs + event.outputs
        )
        if event.event_id in event_ids or (edgeless and incident):
            result.append(event)
    return result


def _sort_key(projection: Projection, node: str) -> tuple[str, str]:
    return str(projection.nodes[node]["asset_type"]), str(projection.nodes[node]["asset_id"])


def _adjacent(projection: Projection, node: str, direction: str) -> set[str]:
    outgoing = {
        target
        for _, target, edge in projection.out_edges(node, data=True)
        if direction in {"both", "downstream"} or edge["kind"] == "semantic"
    }
    incoming = {
        source
        for source, _, edge in projection.in_edges(node, data=True)
        if direction in {"both", "upstream"} or edge["kind"] == "semantic"
    }
    return outgoing | incoming


def _neighbors(
    projection: Projection, asset: str | None, direction: str, depth: int, max_nodes: int | None
) -> tuple[set[str], bool]:
    limit = len(projection) if max_nodes is None else max_nodes
    roots = [asset] if asset is not None and asset in projection else []
    if asset is None:
        roots = sorted(projection, key=lambda node: _sort_key(projection, node))
    selected: set[str] = set()
    for root in roots:
        if root in selected:
            continue
        if len(selected) >= limit:
            return selected, True
        selected.add(root)
        frontier = {root}
        for _ in range(depth):
            neighbors: set[str] = set()
            for node in frontier:
                neighbors.update(_adjacent(projection, node, direction))
            candidates = sorted(neighbors - selected, key=lambda node: _sort_key(projection, node))
            remaining = limit - len(selected)
            frontier = set(candidates[:remaining])
            selected.update(frontier)
            if len(candidates) > remaining:
                return selected, True
            if not frontier:
                break
    return selected, False


__all__ = ["all_events", "append_event", "graph"]
