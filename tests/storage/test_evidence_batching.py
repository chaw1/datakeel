# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound evidence projection queries while preserving immutable replay semantics."""

from __future__ import annotations

from contextlib import contextmanager
from math import ceil
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event as sql_event
from sqlalchemy import func, select

from datakeel.core.errors import ConflictError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.storage.database import EventRow
from datakeel.storage.evidence_cache import cached_entries, invalidations_for
from datakeel.storage.evidence_decisions import decide_assertions, list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_rows import AssertionRow, EvidenceCacheRow
from datakeel.storage.evidence_store import (
    list_assertions,
    project_bundle,
    record_extraction,
    record_extraction_in_session,
    validated_bundle,
)
from tests.evidence.helpers import extraction_event, fixture_bundle

if TYPE_CHECKING:
    from collections.abc import Iterator

    from datakeel.core.models import LineageEvent
    from datakeel.storage.database import Database


def _batch_event(size: int, run: str = "batch") -> LineageEvent:
    event = extraction_event(run)
    template = fixture_bundle(event)
    assertion = template.assertions[0]
    entry = template.cache_entries[0]
    subjects = [entry.subject.model_copy(update={"asset_id": f"image-{i}"}) for i in range(size)]
    assertions = tuple(
        assertion.model_copy(
            update={
                "id": f"assertion-{run}-{i}",
                "subject": subject,
                "anchors": (assertion.anchors[0].model_copy(update={"asset_ref": subject}),),
            }
        )
        for i, subject in enumerate(subjects)
    )
    bundle = KnowledgeBundle(
        run_id=run,
        assertions=assertions,
        cache_entries=tuple(
            entry.model_copy(update={"subject": item.subject, "assertion_ids": (item.id,)})
            for item in assertions
        ),
    )
    return event.model_copy(
        update={
            "inputs": subjects,
            "params": {"run_id": run, "knowledge_bundle": bundle.model_dump(mode="json")},
        }
    )


@contextmanager
def _statements(db: Database) -> Iterator[list[str]]:
    statements: list[str] = []

    def track(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy event callback signature.
    ) -> None:
        statements.append(statement)

    sql_event.listen(db.engine, "before_cursor_execute", track)
    try:
        yield statements
    finally:
        sql_event.remove(db.engine, "before_cursor_execute", track)


@pytest.mark.parametrize("size", [1, 1200])
def test_fresh_extraction_queries_scale_by_batch_and_keep_cache_hits(
    db: Database, size: int
) -> None:
    """Avoid per-observation reads or autoflushes even across SQL parameter chunks."""
    event = _batch_event(size)
    with _statements(db) as statements:
        record_extraction(db, event)
    assert sum(sql.startswith("SELECT") for sql in statements) <= 1 + 4 * ceil(size / 500)
    assert sum(sql.startswith("INSERT") for sql in statements) <= 4
    assert len(list_assertions(db)) == size
    assert len(cached_entries(db, fixture_bundle(event).cache_entries)) == size


def test_invalidations_load_prior_assertions_in_bounded_batches(db: Database) -> None:
    """Read superseded observations in bulk without changing decision order or reasons."""
    record_extraction(db, _batch_event(1200))
    replacement = _batch_event(1200, "replacement")
    with db.session() as session, _statements(db) as statements:
        decisions = invalidations_for(session, fixture_bundle(replacement), replacement)
    assert sum(sql.startswith("SELECT") for sql in statements) <= 6
    assert [item.assertion_id for item in decisions] == [
        f"assertion-batch-{i}" for i in range(1200)
    ]
    assert all(item.reason == "superseded_extraction" for item in decisions)


def test_batch_replacement_retry_and_rebuild_preserve_audits(db: Database) -> None:
    """Keep predecessor links, invalidations and idempotent replay for whole batches."""
    first = record_extraction(db, _batch_event(24))
    replacement = _batch_event(24, "replacement")
    second = record_extraction(db, replacement)
    assert validated_bundle(second).prior_cache_event_ids == (first.event_id,)
    decisions = list_decisions(db)
    assert len(decisions) == 24
    assert record_extraction(db, replacement) == second
    assert record_extraction(db, second) == second
    assert list_decisions(db) == decisions
    assert len(list_assertions(db)) == 24
    assert len(list_assertions(db, include_invalidated=True)) == 48
    assert rebuild_evidence(db).matches
    assert list_decisions(db) == decisions


def test_batch_immutable_conflict_rolls_back_new_observations(db: Database) -> None:
    """Discard new entries and their event when the last observation conflicts."""
    record_extraction(db, _batch_event(3))
    replacement = _batch_event(3, "replacement")
    bundle = fixture_bundle(replacement)
    conflict = bundle.assertions[-1].model_copy(update={"id": "assertion-batch-2"})
    bundle = bundle.model_copy(
        update={"assertions": (*bundle.assertions[:-1], conflict), "cache_entries": ()}
    )
    with pytest.raises(ConflictError, match="immutable content"):
        record_extraction(db, replacement, bundle)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(EventRow)) == 1
        assert session.scalar(select(func.count()).select_from(AssertionRow)) == 3
    assert not list_decisions(db)


def test_duplicate_cache_slots_preserve_last_entry_without_duplicate_rows(db: Database) -> None:
    """Preserve ordered slot replacement while pending rows await the batch flush."""
    event = _batch_event(1)
    bundle = fixture_bundle(event)
    first = bundle.cache_entries[0]
    last = first.model_copy(update={"output": {"result": "last"}})
    bundle = bundle.model_copy(update={"cache_entries": (first, last)})
    record_extraction(db, event, bundle)
    assert cached_entries(db, (first,)) == (last,)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(EvidenceCacheRow)) == 1
    assert rebuild_evidence(db).matches


def test_reprojecting_equal_payload_retains_review_and_invalidation_overlay(db: Database) -> None:
    """Never reset reviewed or inactive state when immutable payload already matches."""
    event = _batch_event(1)
    bundle = fixture_bundle(event)
    record_extraction(db, event)
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(bundle.assertions[0].id,),
            status="accepted",
            actor="reviewer",
            idempotency_key="batch-review",
        ),
    )
    with db.session() as session:
        row = session.get(AssertionRow, bundle.assertions[0].id)
        assert row is not None
        row.active = False
        before = (row.status, row.decided_by, row.decided_at)
        project_bundle(session, event, bundle)
        session.commit()
        assert (row.status, row.decided_by, row.decided_at) == before
        assert not row.active
    assert not list_assertions(db)
    assert list_assertions(db, include_invalidated=True)[0].status == "accepted"


def test_cache_replacement_updates_preloaded_session_identity(db: Database) -> None:
    """Keep existing ORM references consistent while inserting new rows in bulk."""
    first = _batch_event(1)
    entry = fixture_bundle(first).cache_entries[0]
    record_extraction(db, first)
    second = _batch_event(2, "replacement")
    replacement = fixture_bundle(second).cache_entries[0]
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(EvidenceCacheRow, entry.slot)
        assert row is not None
        record_extraction_in_session(session, second)
        assert row.payload == replacement.model_dump(mode="json")
        assert row.producer_event_id == second.event_id
        session.commit()
    assert len(cached_entries(db, fixture_bundle(second).cache_entries)) == 2
