# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publication ordering and deterministic offline interleaving; no PG mutex simulation."""

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.models import LineageEvent, new_id
from datakeel.core.vector_results import VectorCacheProduct
from datakeel.dataset_store.rows import EventRow
from datakeel.storage import evidence_store
from datakeel.storage.database import Database
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.vector_helpers import vector_dataset, vector_run
from tests.storage.test_evidence_batching import _batch_event


def _fresh_embed(
    db: Database, tmp_path: Path
) -> Callable[[], tuple[LineageEvent, KnowledgeBundle]]:
    run = vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    assert run.state == "COMPLETED", run.error
    with db.session() as session:
        template = next(
            LineageEvent.model_validate(row.payload)
            for row in session.scalars(select(EventRow))
            if row.payload.get("operator") == "evidence.vector_embed"
        )
    base = evidence_store.validated_bundle(template)

    def clone() -> tuple[LineageEvent, KnowledgeBundle]:
        identifier = new_id()
        event = template.model_copy(
            update={
                "event_id": identifier,
                "idempotency_key": identifier,
                "source_ref": identifier,
                "params": {
                    **{
                        key: value
                        for key, value in template.params.items()
                        if key != "knowledge_bundle"
                    },
                    "run_id": identifier,
                },
            }
        )
        return event, base.model_copy(
            update={"run_id": identifier, "invalidations": (), "prior_cache_event_ids": ()}
        )

    return clone


def test_first_vector_reads_follow_projection_lock(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every predecessor/cache invalidation helper runs after the first shared lock."""
    event, bundle = _fresh_embed(db, tmp_path)()
    held = False
    reads: list[str] = []

    def acquire(session: Session) -> None:
        nonlocal held
        held = True

    def guarded(name: str) -> Callable[..., object]:
        original = getattr(evidence_store, name)

        def read(*args: object, **kwargs: object) -> object:
            assert held, f"{name} executes before the first projection lock"
            reads.append(name)
            return original(*args, **kwargs)

        return read

    monkeypatch.setattr(evidence_store, "lock_evidence", acquire)
    for name in (
        "cache_predecessors",
        "kg_predecessors",
        "vector_predecessors",
        "invalidations_for",
    ):
        monkeypatch.setattr(evidence_store, name, guarded(name))
    evidence_store.record_extraction(db, event, bundle)
    assert set(reads) == {
        "cache_predecessors",
        "kg_predecessors",
        "vector_predecessors",
        "invalidations_for",
    }


def test_ordinary_publication_never_calls_projection_lock(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordinary publication preserves its batching budget without vector lock calls."""
    calls: list[Session] = []

    monkeypatch.setattr(evidence_store, "lock_evidence", calls.append)
    evidence_store.record_extraction(db, _batch_event(2, "ordinary-lock"))
    assert not calls, "ordinary extraction acquired vector projection lock"


def test_direct_vector_project_still_locks_before_diff_reads(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct replay/project callers still enter the same lock before deriving their diff."""
    event, bundle = _fresh_embed(db, tmp_path)()
    recorded = evidence_store.record_extraction(db, event, bundle)
    held = False
    original = evidence_store.vector_predecessors

    def acquire(session: Session) -> None:
        nonlocal held
        held = True

    def read(session: Session, products: tuple[VectorCacheProduct, ...]) -> tuple[str, ...]:
        assert held, "direct project read before projection lock"
        return original(session, products)

    monkeypatch.setattr(evidence_store, "lock_evidence", acquire)
    monkeypatch.setattr(evidence_store, "vector_predecessors", read)
    with db.session() as session:
        evidence_store.project_bundle(session, recorded, evidence_store.validated_bundle(recorded))
        session.commit()
    assert held


def test_same_key_publication_committed_before_lock_grant_is_not_rejected(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B commits while A awaits its first lock; A must derive its diff from B, not old E.

    SQLite's BEGIN IMMEDIATE is deliberately absent on A. The scheduling hook supplies
    B before A's lock grant, not inside A's locked reads. This is not a PG concurrency test.
    """
    clone = _fresh_embed(db, tmp_path)
    first, first_bundle = clone()
    second, second_bundle = clone()
    interleaved = False
    second_result: LineageEvent | None = None
    original = evidence_store.lock_evidence
    original_read = evidence_store.vector_predecessors

    def publish_second() -> None:
        nonlocal interleaved, second_result
        if not interleaved:
            interleaved = True
            second_result = evidence_store.record_extraction(db, second, second_bundle)

    def acquire(session: Session) -> None:
        publish_second()
        original(session)

    def read(session: Session, products: tuple[VectorCacheProduct, ...]) -> tuple[str, ...]:
        predecessors = original_read(session, products)
        # Negative control: without an entry lock, B can commit in the old read window.
        publish_second()
        return predecessors

    monkeypatch.setattr(evidence_store, "lock_evidence", acquire)
    monkeypatch.setattr(evidence_store, "vector_predecessors", read)
    result: LineageEvent | None = None
    rejection: str | None = None
    with db.session() as session:
        try:
            result = evidence_store.record_extraction_in_session(session, first, first_bundle)
            session.commit()
        except ValidationError as error:
            rejection = str(error)
    assert rejection is None, f"legal same-key publication rejected: {rejection}"
    assert result is not None
    assert second_result is not None
    assert evidence_store.validated_bundle(result).prior_cache_event_ids == (second.event_id,)
    with db.session() as session:
        producers = set(session.scalars(select(VectorCacheRow.producer_event_id)))
        assert first.event_id in producers
        assert second.event_id not in producers
        assert session.get(EventRow, first.event_id) is not None
        assert session.get(EventRow, second.event_id) is not None
