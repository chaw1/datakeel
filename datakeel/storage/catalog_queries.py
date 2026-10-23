# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded typed catalog reads and downstream impact without a second fact store."""

from collections import deque

from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogPage,
    CatalogQuery,
    CatalogSnapshot,
    ImpactResult,
)
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.metrics.projection import resolved_metric_cards
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database

MAX_IMPACT_HOPS = 3


def get_object(db: Database, asset_id: str) -> CatalogObject:
    """Read one stable metadata identity or report its absence explicitly."""
    with db.session() as session:
        for item in _resolved_objects(read_snapshot(session)):
            if item.asset_ref.asset_id == asset_id:
                return item
    msg = f"Catalog object not found: {asset_id}"
    raise NotFoundError(msg)


def read_objects(db: Database, query: CatalogQuery | None = None) -> CatalogPage:
    """List deterministic pages with optional type, source, containment, and name filters."""
    query = query or CatalogQuery()
    with db.session() as session:
        snapshot = read_snapshot(session)
    children = {
        link.target.asset_id
        for link in snapshot.links
        if link.kind == "contains" and link.source.asset_id == query.parent_id
    }
    items = [
        item
        for item in _resolved_objects(snapshot)
        if (
            (query.kind is None or item.asset_ref.asset_type == query.kind)
            and (query.source_id is None or item.source_id == query.source_id)
            and (query.parent_id is None or item.asset_ref.asset_id in children)
            and (query.search is None or query.search.casefold() in item.name.casefold())
        )
    ]
    return CatalogPage(
        items=tuple(items[query.offset : query.offset + query.limit]),
        total=len(items),
        offset=query.offset,
        limit=query.limit,
    )


def neighbors(db: Database, asset_id: str) -> ImpactResult:
    """Read direct neighbors from the latest authoritative scope snapshots."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    links = tuple(
        link for link in snapshot.links if asset_id in {link.source.asset_id, link.target.asset_id}
    )
    ids = {ref.asset_id for link in links for ref in (link.source, link.target)}
    return ImpactResult(
        asset_id=asset_id,
        objects=tuple(item for item in snapshot.objects if item.asset_ref.asset_id in ids),
        links=links,
    )


def _downstream(snapshot: CatalogSnapshot) -> dict[str, list[tuple[str, CatalogLink]]]:
    result: dict[str, list[tuple[str, CatalogLink]]] = {}
    for link in snapshot.links:
        source, target = link.source.asset_id, link.target.asset_id
        if link.kind in {"measures", "means"} or (
            link.kind == "contains" and link.target.asset_type == "column"
        ):
            source, target = target, source
        elif link.kind not in {"derived", "sliced_by"}:
            continue
        result.setdefault(source, []).append((target, link))
    return result


def impact(db: Database, asset_id: str, max_nodes: int = 200) -> ImpactResult:
    """Follow column derivation and inverse semantic dependencies within a hard bound."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    if asset_id not in {item.asset_ref.asset_id for item in snapshot.objects}:
        msg = f"Catalog object not found: {asset_id}"
        raise NotFoundError(msg)
    adjacency = _downstream(snapshot)
    visited = {asset_id}
    queue = deque([(asset_id, 0)])
    links: list[CatalogLink] = []
    truncated = False
    while queue:
        identity, depth = queue.popleft()
        if depth >= MAX_IMPACT_HOPS:
            continue
        for target, link in adjacency.get(identity, []):
            if target not in visited:
                if len(visited) >= max_nodes:
                    truncated = True
                    continue
                visited.add(target)
                queue.append((target, depth + 1))
            links.append(link)
    return ImpactResult(
        asset_id=asset_id,
        objects=tuple(item for item in snapshot.objects if item.asset_ref.asset_id in visited),
        links=tuple(links),
        truncated=truncated,
    )


def _resolved_objects(snapshot: CatalogSnapshot) -> tuple[CatalogObject, ...]:
    cards = {item.definition.id: item for item in resolved_metric_cards(snapshot)}
    return tuple(
        item.model_copy(
            update={
                "properties": JsonDocument(cards[item.asset_ref.asset_id].model_dump(mode="json"))
            }
        )
        if item.asset_ref.asset_type == "metric"
        else item
        for item in snapshot.objects
    )
