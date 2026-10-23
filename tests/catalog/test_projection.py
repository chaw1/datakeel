# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog projections are disposable and their normalized content is reproducible."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from datakeel.catalog.service import import_catalog
from datakeel.lineage.models import GraphQuery
from datakeel.storage.catalog_projection import projection_hash, rebuild_catalog
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.events import all_events
from datakeel.storage.lineage_service import get_graph

if TYPE_CHECKING:
    from datakeel.core.catalog_models import CatalogImportRequest
    from datakeel.storage.database import Database


def test_rebuild_when_projection_deleted_restores_expected_hash(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Replay authoritative snapshots after both derived tables are deliberately cleared."""
    report = import_catalog(db, source_request)
    expected = projection_hash(db)
    with db.session() as session:
        assert session.scalar(select(CatalogEdgeRow)) is not None
        session.execute(delete(CatalogEdgeRow))
        session.execute(delete(CatalogObjectRow))
        session.commit()
    result = rebuild_catalog(db, expected)
    assert result.matches
    assert result.after_hash == expected
    assert result.objects == report.object_count
    assert result.edges == report.link_count
    with db.session() as session:
        assert len(all_events(session)) == 1


def test_rebuild_when_hash_mismatches_reports_without_fabricating_success(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Return a failed comparison while leaving the rebuilt projection available."""
    import_catalog(db, source_request)
    result = rebuild_catalog(db, "not-the-current-hash")
    assert not result.matches
    assert result.objects > 0
    assert rebuild_catalog(db).matches


def test_catalog_graph_when_references_present_preserves_relation_kind(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Keep reflected foreign keys distinguishable from SQL-derived lineage."""
    import_catalog(db, source_request)
    graph = get_graph(
        db, query=GraphQuery(asset_id="sample/main/sales/region_id", hops=1, include_catalog=True)
    )
    assert any(edge.link_type == "references" and edge.kind == "catalog" for edge in graph.edges)
