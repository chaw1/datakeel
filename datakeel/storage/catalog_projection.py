# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuild separate catalog object and edge projections from their immutable events."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from datakeel.core.catalog_canonical import canonical_content, document_hash
from datakeel.core.catalog_models import CatalogRebuildResult, CatalogSnapshot
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.database import Database
from datakeel.storage.events import all_events

PROJECTOR_VERSION = "1.0"


def project_snapshot(session: Session, snapshot: CatalogSnapshot) -> None:
    """Replace a scope's disposable rows while preserving every historical event."""
    session.execute(delete(CatalogEdgeRow).where(CatalogEdgeRow.scope == snapshot.scope))
    session.execute(delete(CatalogObjectRow).where(CatalogObjectRow.scope == snapshot.scope))
    session.flush()
    for item in snapshot.objects:
        session.add(
            CatalogObjectRow(
                asset_id=item.asset_ref.asset_id,
                scope=snapshot.scope,
                kind=item.asset_ref.asset_type,
                payload=JsonDocument.model_validate(item.model_dump(mode="json")).root,
            )
        )
    for link in snapshot.links:
        payload = JsonDocument.model_validate(link.model_dump(mode="json"))
        identity = JsonDocument(
            {
                "scope": snapshot.scope,
                "kind": link.kind,
                "source": link.source.asset_id,
                "target": link.target.asset_id,
            }
        )
        session.add(
            CatalogEdgeRow(
                id=document_hash(identity),
                scope=snapshot.scope,
                kind=link.kind,
                source_id=link.source.asset_id,
                target_id=link.target.asset_id,
                producer_event_id=link.producer_event_id or "",
                payload=payload.root,
            )
        )
    session.flush()


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
        for _event, snapshot in history:
            project_snapshot(session, snapshot)
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
