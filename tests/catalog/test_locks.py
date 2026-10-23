# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Concurrent catalog operations preserve event identity and their rebuildable projection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import TYPE_CHECKING

from datakeel.catalog.service import prepare_import
from datakeel.storage.catalog_projection import projection_hash, rebuild_catalog
from datakeel.storage.catalog_store import lock_catalog, publish_snapshot
from datakeel.storage.events import all_events

if TYPE_CHECKING:
    from datakeel.core.catalog_models import CatalogImportRequest, ImportReport
    from datakeel.storage.database import Database


def test_publish_when_concurrent_replays_serializes_into_one_event(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Two import transactions cannot both publish the same source version."""
    snapshot, _ = prepare_import(source_request)
    barrier = Barrier(2)

    def publish() -> ImportReport:
        barrier.wait(timeout=10)
        return publish_snapshot(db, snapshot)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish) for _ in range(2)]
        reports = [future.result(timeout=20) for future in futures]
    assert sum(report.event_id is not None for report in reports) == 1
    with db.session() as session:
        assert len(all_events(session)) == 1
    assert rebuild_catalog(db).matches


def test_rebuild_when_publication_is_concurrent_preserves_committed_projection(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A rebuild and a changed import share a fence and cannot lose committed metadata."""
    snapshot, _ = prepare_import(source_request)
    publish_snapshot(db, snapshot)
    changed = snapshot.model_copy(
        update={
            "objects": (
                snapshot.objects[0].model_copy(update={"name": "Renamed"}),
                *snapshot.objects[1:],
            )
        }
    )
    barrier = Barrier(2)

    def publish() -> None:
        barrier.wait(timeout=10)
        publish_snapshot(db, changed)

    def rebuild() -> None:
        barrier.wait(timeout=10)
        rebuild_catalog(db)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish), executor.submit(rebuild)]
        for future in futures:
            future.result(timeout=20)
    expected = projection_hash(db)
    assert rebuild_catalog(db, expected).matches
    with db.session() as session:
        assert len(all_events(session)) == 2


def test_catalog_lock_when_reentered_preserves_callers_transaction(db: Database) -> None:
    """An action may acquire the same fence before a publisher without nested BEGIN."""
    with db.session() as session:
        db.lock_writes(session)
        lock_catalog(session)
        lock_catalog(session)
        session.commit()
