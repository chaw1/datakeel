# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable artifact verification and deterministic projection replay ordering."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_cache import KnowledgeBundleArtifact
from datakeel.storage.evidence_artifacts import load_bundle, publish_bundle
from datakeel.storage.evidence_cache import cached_entry
from datakeel.storage.evidence_projection import (
    PROJECTOR_VERSION,
    ordered_bundles,
    projection_hash,
    rebuild_evidence,
)
from datakeel.storage.evidence_store import list_assertions, record_extraction
from datakeel.storage.objects import object_store
from tests.evidence.helpers import extraction_event, fixture_bundle

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_artifact_integrity_and_output_reference_are_verified(db: Database) -> None:
    """Reject mutated objects and lineage output references before constructing assertions."""
    event = record_extraction(db, extraction_event())
    artifact = KnowledgeBundleArtifact.model_validate(event.params["knowledge_bundle"])
    with pytest.raises(ValidationError, match="hash or output"):
        load_bundle(event.model_copy(update={"outputs": []}))
    object_store().materialize(artifact.object_key).write_text("{}")
    with pytest.raises(ValidationError, match="hash or output"):
        load_bundle(event)


def test_canonical_hash_matches_fixed_fields_and_projector_version(db: Database) -> None:
    """Use only the specified semantic fields while retaining the projector format identity."""
    record_extraction(db, extraction_event())
    fields = {
        "subject",
        "predicate",
        "object",
        "status",
        "anchors",
        "extractor",
        "producer_event_id",
    }
    content = {
        "projector_version": PROJECTOR_VERSION,
        "assertions": [
            item.model_dump(mode="json", include=fields) for item in list_assertions(db)
        ],
    }
    expected = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert projection_hash(db) == expected


def test_replay_respects_cache_predecessors_at_identical_timestamps(db: Database) -> None:
    """Keep the newest cache result when event identifiers sort against publication order."""
    first = extraction_event("z-first")
    second = extraction_event("a-second", version="2").model_copy(
        update={"occurred_at": first.occurred_at}
    )
    record_extraction(db, first)
    record_extraction(db, second)
    assert rebuild_evidence(db).matches
    entry = fixture_bundle(second).cache_entries[0]
    assert cached_entry(db, entry.subject, entry.key) == entry


def test_replay_rejects_missing_and_cyclic_cache_predecessors(db: Database) -> None:
    """Never silently guess a projection order for malformed artifact dependencies."""
    original = extraction_event()
    bundle = fixture_bundle(original)
    event = publish_bundle(
        original, bundle.model_copy(update={"prior_cache_event_ids": ("missing",)})
    )
    with pytest.raises(ValidationError, match="missing"):
        ordered_bundles([event])
    event = publish_bundle(
        original, bundle.model_copy(update={"prior_cache_event_ids": (original.event_id,)})
    )
    with pytest.raises(ValidationError, match="cycle"):
        ordered_bundles([event])
