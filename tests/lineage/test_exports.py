# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable document vocabulary edge cases remain explicit."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.exports import export_croissant
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.lineage_service import export_events, record_event

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_croissant_plain_license_and_publication_date_are_preserved() -> None:
    """Verify croissant plain license and publication date are preserved."""
    document = export_croissant(
        {"id": "example", "license": "MIT", "created_at": date(2026, 10, 22)}, []
    )
    assert document["license"] == {"@type": "CreativeWork", "name": "MIT"}
    assert document["datePublished"] == "2026-10-22"


def test_dataset_export_preserves_failed_observation_without_fabricated_outputs(
    db: Database, tmp_path: Path
) -> None:
    """Verify dataset export preserves failed observation without fabricated outputs."""
    source = tmp_path / "generated.txt"
    source.write_text("Generated export fixture")
    dataset = import_paths(db, "failure-export", [source])
    event = LineageEvent(
        idempotency_key="failed-export",
        operator="fixture.failure",
        run_state="FAILED",
        inputs=[AssetRef(asset_id=dataset.id)],
        outputs=[],
    )
    assert record_event(db, event)
    documents = export_events(db, dataset.id)
    failures = [document for document in documents if document["eventType"] == "FAIL"]
    assert len(failures) == 1
    assert failures[0]["outputs"] == []
    assert failures[0]["run"]["facets"]["datakeel_execution"]["eventId"] == event.event_id
