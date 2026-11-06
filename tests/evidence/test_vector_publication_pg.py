# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real PostgreSQL publication scheduling and shared publication/review/rebuild exclusion."""

from __future__ import annotations

import json
from math import ceil
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.evidence_cache import EvidenceRebuildResult
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import LineageEvent
from datakeel.dataset_store.rows import EventRow
from datakeel.storage.evidence_decisions import decide_in_session, list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_store import (
    record_extraction,
    record_extraction_in_session,
    validated_bundle,
)
from datakeel.storage.vector_cache import lock_evidence
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.helpers import fixture_bundle
from tests.evidence.pg_fixtures import batch_event, fresh_publication, statements
from tests.pg_evidence_helpers import LockGate, PgJob, PgTrace, pg_trace, require_postgres

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.orm import Session

    from datakeel.core.evidence_cache import KnowledgeBundle
    from datakeel.storage.database import Database

pytestmark = pytest.mark.usefixtures("offline_network")


def _publish(
    trace: PgTrace, session: Session, label: str, value: tuple[LineageEvent, KnowledgeBundle]
) -> LineageEvent:
    result = record_extraction_in_session(session, *value)
    trace.note(f"{label}:predecessors={validated_bundle(result).prior_cache_event_ids}")
    session.commit()
    trace.note(f"{label}:publication-commit:returned")
    return result


def _reads_follow_grant(trace: PgTrace, label: str) -> None:
    calls = [(phase, sql) for owner, phase, sql in trace.sql if owner == label]
    reads = [
        (index, phase, sql)
        for index, (phase, sql) in enumerate(calls)
        if sql.startswith("SELECT") and "pg_backend_pid()" not in sql
    ]
    assert reads
    assert "pg_advisory_xact_lock" in reads[0][2], "publication read before lock dispatch"
    grant = next(
        index for index, phase, sql in reads if phase == "after" and "pg_advisory_xact_lock" in sql
    )
    predecessor_reads = [
        index
        for index, phase, sql in reads
        if phase == "before" and "pg_advisory_xact_lock" not in sql
    ]
    assert predecessor_reads
    assert all(index > grant for index in predecessor_reads), "read before actual PG lock grant"
    assert any("vector_cache" in sql for _, _, sql in reads)


def _verify_producers(
    db: Database, result: LineageEvent, previous: tuple[LineageEvent, ...]
) -> None:
    bundle = validated_bundle(result)
    keys = [f"{p.mode}:{p.implementation}:{p.kind}:{p.key}" for p in bundle.vector_products]
    assert keys
    with db.session() as session:
        rows = list(
            session.scalars(select(VectorCacheRow).where(VectorCacheRow.namespace_key.in_(keys)))
        )
        assert len(rows) == len(keys)
        assert {row.producer_event_id for row in rows} == {result.event_id}
        for event in (*previous, result):
            row = session.get(EventRow, event.event_id)
            assert row is not None
            assert LineageEvent.model_validate(row.payload) == event


def test_same_key_commits_before_actual_grant_supply_the_latest_predecessor(
    db: Database, tmp_path: Path, record_property: Callable[[str, object], None]
) -> None:
    """B/C scheduling is synthetic; A's SQL, wait, grant and post-grant reads are real."""
    require_postgres(db)
    clone = fresh_publication(db, tmp_path)
    a_value, b_value, c_value = clone(), clone(), clone()
    assert a_value[1].vector_products == b_value[1].vector_products == c_value[1].vector_products
    with pg_trace(db, record_property) as trace, trace.session("G") as guard:
        gate = LockGate()
        trace.gates["A"] = gate
        a = PgJob(trace, "A", lambda session: _publish(trace, session, "A", a_value))
        try:
            assert gate.entered.wait(15), "A never reached its first actual advisory SQL"
            with trace.session("B") as session:
                b_result = _publish(trace, session, "B", b_value)
            with trace.session("C") as session:
                c_result = _publish(trace, session, "C", c_value)
            assert validated_bundle(c_result).prior_cache_event_ids == (b_result.event_id,)
            lock_evidence(guard)
            gate.resume.set()
            trace.blocked(a, "G")
            assert trace.count("A") == 0
            trace.note("G:rollback:invoked")
            guard.rollback()
            trace.note("G:rollback:returned")
            result = a.result()
            assert isinstance(result, LineageEvent)
            assert validated_bundle(result).prior_cache_event_ids == (c_result.event_id,)
            trace.note(f"verified:A:predecessor=C:{c_result.event_id}")
            _reads_follow_grant(trace, "A")
            _verify_producers(db, result, (b_result, c_result))
            assert trace.count("A", "before") == trace.count("A") == 1
            trace.ordered(
                "B:publication-commit:returned",
                "C:publication-commit:returned",
                "observer:A:blocked",
                "G:rollback:invoked",
                "A:after: SELECT pg_advisory_xact_lock",
                "A:predecessors=",
                "A:publication-commit:returned",
                "A:completed",
            )
        finally:
            gate.resume.set()
            guard.rollback()
            a.result()


def _competing_operation(
    kind: str,
    db: Database,
    trace: PgTrace,
    value: tuple[LineageEvent, KnowledgeBundle],
    request: AssertionDecisionRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Session], object]:
    def run(session: Session) -> object:
        if kind == "publication":
            return _publish(trace, session, "B", value)
        if kind == "review":
            result = decide_in_session(session, request)
            session.commit()
            trace.note("B:review-commit:returned")
            return result
        # Route only the fixture's Session factory to this worker's real, pinned PG Session.
        # Rebuild, advisory SQL, reads, deletes, replay and commit all run unchanged.
        with monkeypatch.context() as patch:
            patch.setattr(db, "session", lambda: session)
            result = rebuild_evidence(db)
        trace.note("B:rebuild-commit:returned")
        return result

    return run


@pytest.mark.parametrize("kind", ["publication", "review", "rebuild"])
def test_publication_review_and_rebuild_wait_for_the_same_real_lock(
    db: Database,
    tmp_path: Path,
    record_property: Callable[[str, object], None],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """An uncommitted vector publisher excludes each real competing write path."""
    require_postgres(db)
    clone = fresh_publication(db, tmp_path)
    a_value, b_value = clone(), clone()
    ordinary = batch_event(1, "pg-review")
    record_extraction(db, ordinary)
    request = AssertionDecisionRequest(
        assertion_ids=(fixture_bundle(ordinary).assertions[0].id,),
        status="accepted",
        actor="fixture-reviewer",
        idempotency_key="pg-review",
    )
    with pg_trace(db, record_property) as trace, trace.session("A") as holder:
        a_result = record_extraction_in_session(holder, *a_value)
        trace.note("A:publication-staged")
        operation = _competing_operation(kind, db, trace, b_value, request, monkeypatch)
        b = PgJob(trace, "B", operation)
        try:
            trace.blocked(b, "A")
            assert trace.count("B") == 0
            trace.note("A:commit:invoked")
            holder.commit()
            trace.note("A:commit:returned")
            result = b.result()
            assert b.done.is_set()
            assert trace.count("A", "before") == trace.count("A") == 1
            assert trace.count("B", "before") == trace.count("B") == 1
            _verify_competing_result(db, kind, result, a_result)
            trace.ordered(
                "A:publication-staged",
                "observer:B:blocked",
                "A:commit:invoked",
                "B:after: SELECT pg_advisory_xact_lock",
                f"B:{kind}-commit:returned",
                "B:completed",
            )
        finally:
            holder.rollback()
            b.result()


def _verify_competing_result(
    db: Database, kind: str, result: object, a_result: LineageEvent
) -> None:
    if kind == "publication":
        assert isinstance(result, LineageEvent)
        assert validated_bundle(result).prior_cache_event_ids == (a_result.event_id,)
        _verify_producers(db, result, (a_result,))
    else:
        _verify_producers(db, a_result, ())
        if kind == "review":
            decisions = list_decisions(db)
            assert len(decisions) == 1
            assert decisions[0].status == "accepted"
        else:
            assert isinstance(result, EvidenceRebuildResult)
            assert result.matches


@pytest.mark.parametrize("size", [1, 1200])
def test_pg_ordinary_publication_retains_exact_batching_upper_bounds(
    db: Database, record_property: Callable[[str, object], None], size: int
) -> None:
    """Real PG ordinary writes keep the existing five/thirteen SELECT and four INSERT cap."""
    require_postgres(db)
    with pg_trace(db, record_property), statements(db) as sql:
        result = record_extraction(db, batch_event(size, "pg-ordinary"))
    selects = sum(statement.startswith("SELECT") for statement in sql)
    inserts = sum(statement.startswith("INSERT") for statement in sql)
    record_property("pg_batch_sql", json.dumps(sql))
    record_property("pg_batch_selects", selects)
    record_property("pg_batch_inserts", inserts)
    assert selects <= 1 + 4 * ceil(size / 500)
    assert inserts <= 4
    assert not any("pg_advisory_xact_lock" in statement for statement in sql)
    assert not validated_bundle(result).vector_products
