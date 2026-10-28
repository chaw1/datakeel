# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuild separate catalog object and edge projections from their immutable events."""

from itertools import batched

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from datakeel.core.catalog_canonical import canonical_content, document_hash
from datakeel.core.catalog_models import CatalogRebuildResult, CatalogSnapshot
from datakeel.core.catalog_projection import project_catalog, snapshot_events
from datakeel.core.models import JsonDocument
from datakeel.storage.base import Base
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.database import Database
from datakeel.storage.events import all_events

PROJECTOR_VERSION = "1.0"


def project_snapshot(session: Session, snapshot: CatalogSnapshot) -> None:
    """Rebuild the merged projection after a scope's authoritative event was appended."""
    current = project_catalog(all_events(session))
    _write_projection(session, current.model_copy(update={"scope": snapshot.scope}))


def _insert_rows(session: Session, row: type[Base], values: list[dict[str, object]]) -> None:
    """Write rows in few multi-row statements: one statement per row costs a server round trip.

    Each statement stays within the dialect's bound-parameter limit.
    """
    if not values:
        return
    limit = session.get_bind().dialect.insertmanyvalues_max_parameters
    for chunk in batched(values, max(1, limit // len(values[0]))):
        session.execute(insert(row).values(list(chunk)))


def _write_projection(session: Session, snapshot: CatalogSnapshot) -> None:
    session.execute(delete(CatalogEdgeRow))
    session.execute(delete(CatalogObjectRow))
    session.flush()
    objects: list[dict[str, object]] = [
        {
            "asset_id": item.asset_ref.asset_id,
            "scope": snapshot.scope,
            "kind": item.asset_ref.asset_type,
            "payload": JsonDocument.model_validate(item.model_dump(mode="json")).root,
        }
        for item in snapshot.objects
    ]
    edges: list[dict[str, object]] = []
    for link in snapshot.links:
        identity = JsonDocument(
            {
                "scope": snapshot.scope,
                "kind": link.kind,
                "source": link.source.asset_id,
                "target": link.target.asset_id,
            }
        )
        edges.append(
            {
                "id": document_hash(identity),
                "scope": snapshot.scope,
                "kind": link.kind,
                "source_id": link.source.asset_id,
                "target_id": link.target.asset_id,
                "producer_event_id": link.producer_event_id or "",
                "payload": JsonDocument.model_validate(link.model_dump(mode="json")).root,
            }
        )
    _insert_rows(session, CatalogObjectRow, objects)
    _insert_rows(session, CatalogEdgeRow, edges)


def normalized_hash(session: Session) -> str:
    """Hash fixed canonical metadata fields together with the projector version."""
    return document_hash(
        JsonDocument(
            {
                "projector_version": PROJECTOR_VERSION,
                "catalog": canonical_content(read_snapshot(session)).root,
            }
        )
    )


def projection_hash(db: Database) -> str:
    """Read the normalized comparison identity of current catalog rows."""
    with db.session() as session:
        return normalized_hash(session)


def rebuild_catalog(db: Database, expected_hash: str | None = None) -> CatalogRebuildResult:
    """Clear both projections, replay events, and report normalized hash equality."""
    with db.session() as session:
        db.lock_writes(session)
        lock_catalog(session)
        before = expected_hash or normalized_hash(session)
        history = snapshot_events(all_events(session))
        session.execute(delete(CatalogEdgeRow))
        session.execute(delete(CatalogObjectRow))
        _write_projection(session, project_catalog(event for event, _snapshot in history))
        current = read_snapshot(session)
        after = normalized_hash(session)
        result = CatalogRebuildResult(
            before_hash=before,
            after_hash=after,
            matches=before == after,
            objects=len(current.objects),
            edges=len(current.links),
            events=len(history),
        )
        session.commit()
        return result
