# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic extraction, immutable assertion contents, and reversible audit decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import AssetRef
from datakeel.storage.database import EventRow
from datakeel.storage.evidence_decisions import decide_assertions, list_decisions
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow
from datakeel.storage.evidence_store import list_assertions, record_extraction, validated_bundle
from tests.evidence.helpers import extraction_event, fixture_bundle

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_complete_extraction_is_atomic_idempotent_and_provenance_bound(db: Database) -> None:
    """Store assertions only alongside their authoritative extraction event."""
    event = extraction_event()
    recorded = record_extraction(db, event)
    assert record_extraction(db, event) == recorded
    assert list_assertions(db, "image")[0].producer_event_id == event.event_id
    assert not list_assertions(db, "missing")
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(EventRow)) == 1
        assert session.scalar(select(func.count()).select_from(AssertionRow)) == 1
    mismatch = extraction_event("other").model_copy(
        update={"idempotency_key": event.idempotency_key}
    )
    with pytest.raises(ConflictError, match="different run content"):
        record_extraction(db, mismatch)


@pytest.mark.parametrize(
    "update",
    [
        {"event_type": "TRANSFORM"},
        {"run_state": "FAILED"},
        {"operator": "file.transform"},
        {"outputs": [AssetRef(asset_id="semantic-edge")]},
        {"inputs": []},
        {"event_id": "different-producer"},
    ],
)
def test_non_extraction_events_cannot_create_assertions(
    db: Database, update: dict[str, object]
) -> None:
    """Reject forged provenance, unfinished runs, and semantic output edges."""
    with pytest.raises(ValidationError):
        record_extraction(db, extraction_event().model_copy(update=update))
    assert not list_assertions(db)


def test_initial_assertion_cannot_include_human_decisions(db: Database) -> None:
    """Separate extractor observation creation from subsequent manual review."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    assertion = bundle.assertions[0].model_copy(update={"status": "accepted"})
    altered = bundle.model_copy(update={"assertions": (assertion,)})
    with pytest.raises(ValidationError, match="bind this extraction"):
        record_extraction(
            db,
            event.model_copy(
                update={
                    "params": {
                        "run_id": bundle.run_id,
                        "knowledge_bundle": altered.model_dump(mode="json"),
                    }
                }
            ),
        )


def test_decisions_are_reversible_audited_and_leave_immutable_content(db: Database) -> None:
    """Review and reverse status while preserving original extracted assertion bytes."""
    event = extraction_event()
    record_extraction(db, event)
    original = list_assertions(db)[0]
    with db.session() as session:
        initial = session.get(AssertionRow, original.id)
        assert initial is not None
        payload = initial.payload
    request = AssertionDecisionRequest(
        assertion_ids=(original.id,), status="accepted", actor="reviewer", idempotency_key="accept"
    )
    assert decide_assertions(db, request)[0].status == "accepted"
    assert decide_assertions(db, request)[0].status == "accepted"
    assert len(list_decisions(db, original.id)) == 1
    with pytest.raises(ConflictError, match="different parameters"):
        decide_assertions(db, request.model_copy(update={"status": "rejected"}))
    assert (
        decide_assertions(
            db, request.model_copy(update={"status": "rejected", "idempotency_key": "reject"})
        )[0].status
        == "rejected"
    )
    assert (
        decide_assertions(
            db, request.model_copy(update={"status": "candidate", "idempotency_key": "restore"})
        )[0].status
        == "candidate"
    )
    assert [decision.action for decision in list_decisions(db)] == ["accept", "reject", "restore"]
    with db.session() as session:
        final = session.get(AssertionRow, original.id)
        assert final is not None
        assert final.payload == payload


def test_decision_batch_missing_assertion_rolls_back_prior_changes(db: Database) -> None:
    """Keep the complete decision batch atomic if any requested observation is missing."""
    record_extraction(db, extraction_event())
    original = list_assertions(db)[0]
    with pytest.raises(NotFoundError, match="Assertion not found"):
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(original.id, "missing"),
                status="accepted",
                actor="reviewer",
                idempotency_key="batch",
            ),
        )
    assert list_assertions(db)[0].status == "candidate"
    assert not list_decisions(db)


def test_database_guards_assertion_content_and_append_only_audits(db: Database) -> None:
    """Reject direct SQL mutation of immutable payload and audit records."""
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
    for sql in (
        "UPDATE assertions SET predicate='corrupt'",
        "UPDATE assertions SET payload='{}'",
        "DELETE FROM assertion_decisions",
        "UPDATE assertion_decisions SET assertion_id='other'",
    ):
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text(sql))
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(AssertionDecisionRow)) == 1


def test_duplicate_assertion_identity_cannot_overwrite_content(db: Database) -> None:
    """Roll back a second producing event attempting to reuse an immutable identity."""
    first = extraction_event()
    record_extraction(db, first)
    second = extraction_event("second", cache=False)
    bundle = KnowledgeBundle.model_validate(second.params["knowledge_bundle"])
    bundle = bundle.model_copy(
        update={
            "assertions": (bundle.assertions[0].model_copy(update={"id": "assertion-run-one"}),)
        }
    )
    second = second.model_copy(
        update={
            "params": {"run_id": bundle.run_id, "knowledge_bundle": bundle.model_dump(mode="json")}
        }
    )
    with pytest.raises(ConflictError, match="immutable content"):
        record_extraction(db, second)
    with db.session() as session:
        assert session.get(EventRow, second.event_id) is None


def test_lineage_contains_only_bundle_artifact_and_run_identity(db: Database) -> None:
    """Keep semantic assertion bodies in an immutable artifact outside lineage rows."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    recorded = record_extraction(
        db, event.model_copy(update={"params": {"run_id": bundle.run_id}}), bundle
    )
    assert "assertions" not in str(recorded.params)
    assert set(recorded.params["knowledge_bundle"]) == {
        "schema_version",
        "object_key",
        "content_revision",
    }
    assert validated_bundle(recorded).assertions == bundle.assertions
    with pytest.raises(ValidationError, match=r"params.run_id"):
        record_extraction(db, event.model_copy(update={"params": {"run_id": "wrong"}}), bundle)


def test_wrong_asset_type_and_foreign_empty_cache_subject_are_rejected(db: Database) -> None:
    """Prevent same-id assets from another type or cache-only subjects bypassing input checks."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    wrong = event.inputs[0].model_copy(update={"asset_type": "dataset"})
    with pytest.raises(ValidationError, match="inputs"):
        record_extraction(db, event.model_copy(update={"inputs": [wrong]}), bundle)
    foreign = bundle.cache_entries[0].model_copy(update={"subject": wrong, "assertion_ids": ()})
    with pytest.raises(ValidationError, match="Cache subjects"):
        record_extraction(db, event, bundle.model_copy(update={"cache_entries": (foreign,)}))


def test_assertion_and_cache_extractors_match_the_producing_operator(db: Database) -> None:
    """Reject assertion-free cache forgery and observations attributed to another operator."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    other = bundle.assertions[0].extractor.model_copy(update={"id": "evidence.caption_mentions"})
    forged = bundle.assertions[0].model_copy(update={"extractor": other})
    with pytest.raises(ValidationError, match="producing event operator"):
        record_extraction(
            db, event, bundle.model_copy(update={"assertions": (forged,), "cache_entries": ()})
        )
    entry = bundle.cache_entries[0]
    cache_only = entry.model_copy(
        update={"assertion_ids": (), "key": entry.key.model_copy(update={"extractor": other})}
    )
    with pytest.raises(ValidationError, match="producing event operator"):
        record_extraction(
            db, event, bundle.model_copy(update={"assertions": (), "cache_entries": (cache_only,)})
        )
    assert not list_assertions(db)


def test_persisted_artifact_replays_without_duplicate_audits(db: Database) -> None:
    """Accept an event's own stored artifact including derived cache invalidations."""
    first = record_extraction(db, extraction_event())
    second = record_extraction(db, extraction_event("second", version="2"))
    before = list_decisions(db)
    assert record_extraction(db, first) == first
    assert record_extraction(db, second) == second
    assert list_decisions(db) == before
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(EventRow)) == 2
    with pytest.raises(ConflictError, match="immutable stored event"):
        record_extraction(db, second.model_copy(update={"on_behalf_of": "different"}))
    with pytest.raises(ValidationError, match="previously stored"):
        record_extraction(db, second.model_copy(update={"idempotency_key": "missing"}))
