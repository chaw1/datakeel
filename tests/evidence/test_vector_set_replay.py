# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recorded set facts, atomic diff ordering and concurrent rebuild without external effects."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import LineageEvent
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.rows import EventRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import decide_assertions, list_decisions
from datakeel.storage.evidence_projection import (
    evidence_watermark,
    projection_hash,
    rebuild_evidence,
)
from datakeel.storage.evidence_rows import AssertionRow, EvidenceCacheRow
from datakeel.storage.evidence_store import list_assertions, project_bundle, validated_bundle
from datakeel.storage.vector_integrity import validate_vector_bundle
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import vector_dataset, vector_run


def events(db: Database) -> list[LineageEvent]:
    """Read only locally produced generated fixture facts."""
    with db.session() as session:
        return [
            LineageEvent.model_validate(r.payload)
            for r in session.scalars(select(EventRow))
            if "knowledge_bundle" in r.payload.get("params", {})
        ]


def test_set_diff_duplicate_is_noop_and_missing_or_out_of_order_refused(
    db: Database, tmp_path: Path
) -> None:
    """Reapplying a hot or historical diff cannot roll back the current projection."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"same", b"same", b"other"))
    pipeline = set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    vector_run(db, dataset, pipeline)
    cold = events(db)
    vector_run(db, dataset, pipeline)
    recorded = events(db)
    expected = projection_hash(db)
    with db.session() as session:
        for event in reversed(recorded):
            project_bundle(session, event, validated_bundle(event))
        session.commit()
    assert projection_hash(db) == expected
    hot = next(
        e
        for e in recorded
        if e.event_id not in {c.event_id for c in cold}
        and e.operator == "evidence.semantic_cluster"
    )
    with db.session() as session:
        session.execute(delete(EvidenceCacheRow))
        session.execute(delete(VectorCacheRow))
        session.execute(delete(AssertionRow))
        refused = False
        try:
            project_bundle(session, hot, validated_bundle(hot))
        except ValidationError:
            refused = True
        session.rollback()
        assert refused
    assert projection_hash(db) == expected


def test_set_rebuild_rejects_tamper_and_rolls_back_without_network(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hash and closure tampering fail before publication and leave the old projection intact."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"same", b"same", b"other"))
    vector_run(
        db, dataset, set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    )
    event = next(e for e in events(db) if e.operator == "evidence.semantic_cluster")
    bundle = validated_bundle(event)
    changed = bundle.vector_findings[0].model_copy(update={"subject": "other"})

    refused = False
    try:
        validate_vector_bundle(
            event,
            bundle.model_copy(update={"vector_findings": (changed, *bundle.vector_findings[1:])}),
        )
    except VectorError:
        refused = True
    assert refused
    before = projection_hash(db)

    def fail(*args: object, **kwargs: object) -> None:
        pytest.fail("transport or credential constructor used")

    monkeypatch.setattr("datakeel.evidence.vector_transport.FakeVectorTransport", fail)
    monkeypatch.setattr("socket.create_connection", fail)
    monkeypatch.setattr("socket.getaddrinfo", fail)
    assert rebuild_evidence(db).after_hash == before
    assert projection_hash(db) == before


def test_set_concurrent_rebuild_and_review_preserve_audit_and_source_watermark(
    db: Database, tmp_path: Path
) -> None:
    """Serialized SQLite writers retain reviewed state and the append-only decision source."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"same", b"same", b"other"))
    vector_run(
        db, dataset, set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    )
    fact = list_assertions(db)[0]
    with db.session() as session:
        before = evidence_watermark(session)
    request = AssertionDecisionRequest(
        assertion_ids=(fact.id,),
        status="accepted",
        actor="reviewer",
        idempotency_key="parallel-review",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        rebuild = pool.submit(rebuild_evidence, db)
        review = pool.submit(decide_assertions, db, request)
        assert rebuild.result().matches
        assert review.result()[0].status == "accepted"
    assert next(f for f in list_assertions(db) if f.id == fact.id).status == "accepted"
    with db.session() as session:
        after = evidence_watermark(session)
    assert before.bundles == after.bundles
    assert before.decisions != after.decisions
    assert len(list_decisions(db, fact.id)) == 1
    expected = projection_hash(db)
    assert rebuild_evidence(db).after_hash == expected
