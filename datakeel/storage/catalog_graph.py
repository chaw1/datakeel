# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Use indexed catalog adjacency before constructing a bounded lineage projection."""

from sqlalchemy import CompoundSelect, Select, String, cast, func, select, union
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.lineage.models import GraphQuery
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.database import EventRow


def _adjacent(
    frontier: set[str], direction: str
) -> Select[str, str, bool] | CompoundSelect[str, str, bool]:
    statements: list[Select[str, str, bool]] = []
    if direction in {"both", "downstream"}:
        statements.append(
            select(
                CatalogEdgeRow.target_id.label("identity"),
                cast(
                    func.coalesce(
                        CatalogObjectRow.kind,
                        CatalogEdgeRow.payload["target"]["asset_type"].as_string(),
                    ),
                    String,
                ).label("kind"),
                CatalogObjectRow.asset_id.is_(None).label("missing"),
            )
            .join(EventRow, EventRow.event_id == CatalogEdgeRow.producer_event_id)
            .outerjoin(CatalogObjectRow, CatalogObjectRow.asset_id == CatalogEdgeRow.target_id)
            .where(CatalogEdgeRow.source_id.in_(frontier))
        )
    if direction in {"both", "upstream"}:
        statements.append(
            select(
                CatalogEdgeRow.source_id.label("identity"),
                cast(
                    func.coalesce(
                        CatalogObjectRow.kind,
                        CatalogEdgeRow.payload["source"]["asset_type"].as_string(),
                    ),
                    String,
                ).label("kind"),
                CatalogObjectRow.asset_id.is_(None).label("missing"),
            )
            .join(EventRow, EventRow.event_id == CatalogEdgeRow.producer_event_id)
            .outerjoin(CatalogObjectRow, CatalogObjectRow.asset_id == CatalogEdgeRow.source_id)
            .where(CatalogEdgeRow.target_id.in_(frontier))
        )
    return union(*statements) if len(statements) > 1 else statements[0].distinct()


def _selected(session: Session, root: str, query: GraphQuery) -> tuple[set[str], bool] | None:
    selected, frontier = {root}, {root}
    collation = "BINARY" if session.get_bind().dialect.name == "sqlite" else "C"
    for _ in range(query.hops if query.hops is not None else query.depth):
        adjacency = _adjacent(frontier, query.direction).subquery()
        remaining = query.max_nodes - len(selected)
        rows = session.execute(
            select(adjacency.c.identity, adjacency.c.missing)
            .where(adjacency.c.identity.not_in(selected))
            .order_by(
                adjacency.c.missing.desc(),
                adjacency.c.kind.collate(collation),
                adjacency.c.identity.collate(collation),
            )
            .limit(remaining + 1)
        ).all()
        # External endpoint kinds depend on all incident link refs in the full projection.
        # Put missing objects first so a bounded shortlist cannot hide this fallback.
        if any(row[1] for row in rows):
            return None
        candidates = [row[0] for row in rows]
        frontier = set(candidates[:remaining])
        selected.update(frontier)
        if len(candidates) > remaining:
            return selected, True
        if not frontier:
            break
    return selected, False


def focused_snapshot(session: Session, query: GraphQuery) -> tuple[CatalogSnapshot, bool] | None:
    """Read only selected nodes and induced edges for a plain catalog-focused query.

    Collapsed and semantic-overlay queries retain the complete projection path.
    Authoritative events are still read by the caller, preserving their public shape.
    """
    root = query.asset_id or query.asset
    if root is None or query.collapse or query.include_semantic:
        return None
    if session.get(CatalogObjectRow, root) is None:
        return None
    selection = _selected(session, root, query)
    if selection is None:
        return None
    selected, truncated = selection
    objects = tuple(
        CatalogObject.model_validate(row.payload)
        for row in session.scalars(
            select(CatalogObjectRow).where(CatalogObjectRow.asset_id.in_(selected))
        )
    )
    # Column labels include their containing table even when it is outside the BFS.
    tables = {item.table_id for item in objects if item.table_id is not None} - selected
    names = tuple(
        CatalogObject.model_validate(row.payload)
        for row in session.scalars(
            select(CatalogObjectRow).where(CatalogObjectRow.asset_id.in_(tables))
        )
    )
    links = tuple(
        CatalogLink.model_validate(row.payload)
        for row in session.scalars(
            select(CatalogEdgeRow)
            .where(CatalogEdgeRow.source_id.in_(selected), CatalogEdgeRow.target_id.in_(selected))
            .order_by(CatalogEdgeRow.kind, CatalogEdgeRow.source_id, CatalogEdgeRow.target_id)
        )
    )
    return CatalogSnapshot(scope="current", objects=(*objects, *names), links=links), truncated


def graph_catalog(session: Session, query: GraphQuery) -> tuple[CatalogSnapshot | None, bool]:
    """Choose an indexed focus or retain the complete overlay for broader queries."""
    if not query.include_catalog:
        return None, False
    focused = focused_snapshot(session, query)
    return focused if focused is not None else (read_snapshot(session), False)
