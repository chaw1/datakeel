# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recorded computation integrity, ordering and human decisions during offline rebuild."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import LineageEvent
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.rows import EventRow
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_projection import ordered_bundles, projection_hash, rebuild_evidence
from datakeel.storage.evidence_store import list_assertions, validated_bundle
from datakeel.storage.vector_integrity import validate_vector_bundle
from tests.evidence.vector_helpers import vector_dataset, vector_run

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _events(db: Database) -> list[LineageEvent]:
    with db.session() as session:
        return [
            LineageEvent.model_validate(row.payload)
            for row in session.scalars(select(EventRow))
            if "knowledge_bundle" in row.payload.get("params", {})
        ]


def test_vector_replay_orders_predecessors_and_rejects_missing_parent(
    db: Database, tmp_path: Path
) -> None:
    """Hot cache replacements have explicit predecessors, independent of incoming event order."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    vector_run(db, dataset)
    vector_run(db, dataset)
    events = _events(db)
    forward = ordered_bundles(events)
    assert ordered_bundles(list(reversed(events))) == forward
    depended = {parent for _, bundle in forward for parent in bundle.prior_cache_event_ids}
    assert depended
    with pytest.raises(ValidationError, match="predecessor event is missing"):
        ordered_bundles([event for event in events if event.event_id not in depended])


def test_vector_bundle_rejects_changed_measurement_status_and_mode(
    db: Database, tmp_path: Path
) -> None:
    """Immutable bundles cannot replay tampered vectors, pairs or fake provenance."""
    vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    event = next(event for event in _events(db) if event.operator == "evidence.semantic_duplicate")
    bundle = validated_bundle(event)
    pair = bundle.vector_pairs[0]
    changed = pair.model_copy(
        update={"measurement": pair.measurement.model_copy(update={"similarity": 0.123})}
    )
    with pytest.raises(VectorError, match="integrity"):
        validate_vector_bundle(
            event, bundle.model_copy(update={"vector_pairs": (changed, *bundle.vector_pairs[1:])})
        )
    bad_sample = bundle.vector_samples[0].model_copy(update={"content_revision": "a" * 64})
    with pytest.raises(VectorError, match="integrity"):
        validate_vector_bundle(
            event,
            bundle.model_copy(update={"vector_samples": (bad_sample, *bundle.vector_samples[1:])}),
        )
    with pytest.raises(VectorError, match="integrity"):
        validate_vector_bundle(
            event.model_copy(update={"params": {**event.params, "mode": "real"}}), bundle
        )


def test_rebuild_keeps_review_overlay_and_compute_hash_independent(
    db: Database, tmp_path: Path
) -> None:
    """Human decisions change fact projection identity and never change recorded computation."""
    vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    events = _events(db)
    computes = [event.quality["vector"]["canonical_hash"] for event in events]
    before = projection_hash(db)
    assertion = list_assertions(db)[0]
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(assertion.id,),
            status="accepted",
            actor="reviewer",
            idempotency_key="vector-review",
        ),
    )
    reviewed = projection_hash(db)
    assert reviewed != before
    assert rebuild_evidence(db).after_hash == reviewed
    assert [event.quality["vector"]["canonical_hash"] for event in _events(db)] == computes
