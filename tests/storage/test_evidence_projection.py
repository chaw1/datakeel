# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content invalidation history and normalized replay from immutable source events."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.evidence_models import AssertionDecision, AssertionDecisionRequest
from datakeel.storage.evidence_cache import cached_entry
from datakeel.storage.evidence_decisions import apply_decision, decide_assertions, list_decisions
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import list_assertions, record_extraction, validated_bundle
from tests.evidence.helpers import extraction_event, fixture_bundle

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_cache_version_changes_invalidate_with_audits_and_rebuild(db: Database) -> None:
    """Keep old immutable assertions but remove them from active evidence queries."""
    first = extraction_event()
    first_bundle = fixture_bundle(first)
    entry = first_bundle.cache_entries[0]
    assert cached_entry(db, entry.subject, entry.key) is None
    record_extraction(db, first)
    assert cached_entry(db, entry.subject, entry.key) == entry
    second = extraction_event("second", version="2")
    new_entry = fixture_bundle(second).cache_entries[0]
    assert cached_entry(db, new_entry.subject, new_entry.key) is None
    record_extraction(db, second)
    assert len(list_assertions(db)) == 1
    assert len(list_assertions(db, include_invalidated=True)) == 2
    assert list_decisions(db)[0].reason == "extractor_version_changed"
    assert cached_entry(db, entry.subject, entry.key) is None
    assert cached_entry(db, new_entry.subject, new_entry.key) == new_entry
    result = rebuild_evidence(db)
    assert result.matches
    assert result.assertions == 2
    assert result.events == 2


def test_cache_all_inputs_invalidate_and_deleted_projection_cannot_hit(db: Database) -> None:
    """Treat any actual content change as cache invalidation and require live assertions."""
    record_extraction(db, extraction_event())
    second = extraction_event("second", content="b")
    record_extraction(db, second)
    assert list_decisions(db)[0].reason == "input_content_or_selector_changed"
    entry = fixture_bundle(second).cache_entries[0]
    with db.session() as session:
        session.execute(delete(AssertionRow))
        session.commit()
    assert cached_entry(db, entry.subject, entry.key) is None


def test_rebuild_after_clear_preserves_decisions_and_original_hash(db: Database) -> None:
    """Reconstruct all content and human review state after discarding derived rows."""
    record_extraction(db, extraction_event())
    assertion = list_assertions(db)[0]
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(assertion.id,),
            status="accepted",
            actor="reviewer",
            idempotency_key="review",
        ),
    )
    expected = projection_hash(db)
    with db.session() as session:
        session.execute(delete(AssertionRow))
        session.commit()
    result = rebuild_evidence(db, expected)
    assert result.matches
    assert list_assertions(db)[0].status == "accepted"
    assert projection_hash(db) == expected
    assert rebuild_evidence(db).matches


def test_invalidations_cannot_be_supplied_by_extractors(db: Database) -> None:
    """Keep cache expiration decisions derived from the stored predecessor inputs."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    decision = AssertionDecision(
        assertion_id="old",
        action="invalidate",
        previous_status="candidate",
        status="candidate",
        actor="extractor",
        reason="forged",
        producer_event_id=event.event_id,
    )
    altered = bundle.model_copy(update={"invalidations": (decision,)})
    event = event.model_copy(
        update={
            "params": {"run_id": bundle.run_id, "knowledge_bundle": altered.model_dump(mode="json")}
        }
    )
    with pytest.raises(ValidationError, match="derived by storage"):
        record_extraction(db, event)
    mismatched = altered.model_copy(
        update={"invalidations": (decision.model_copy(update={"producer_event_id": "wrong"}),)}
    )
    with pytest.raises(ValidationError, match="producing extraction"):
        validated_bundle(event, mismatched)
    with db.session() as session, pytest.raises(NotFoundError, match="Assertion not found"):
        apply_decision(session, decision)


def test_rebuild_empty_store_and_reextraction_audits_superseded_results(db: Database) -> None:
    """Leave an empty projection stable and audit replacing an identical cache slot."""
    assert rebuild_evidence(db).matches
    record_extraction(db, extraction_event())
    record_extraction(db, extraction_event("second"))
    assert list_decisions(db)[0].reason == "superseded_extraction"
    assert len(list_assertions(db)) == 1
    assert rebuild_evidence(db).matches
