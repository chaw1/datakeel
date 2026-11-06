# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real Session lifecycles with local SQL substitution, not PostgreSQL lock measurements."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from datakeel.storage.vector_cache import lock_evidence


@contextmanager
def _lock_dispatch() -> Iterator[tuple[Session, list[str]]]:
    engine = create_engine("sqlite://")
    # Keep the actual SQLite dialect/driver; only select the PG dispatch branch.
    engine.dialect.name = "postgresql"
    calls: list[str] = []

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def substitute(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy callback signature.
    ) -> tuple[str, object]:
        if "pg_advisory_xact_lock" in statement:
            calls.append(statement)
            return "SELECT 1", ()
        return statement, parameters

    try:
        with Session(engine) as session:
            yield session, calls
    finally:
        engine.dispose()


def test_repeated_calls_in_one_transaction_execute_once() -> None:
    """Even unrelated Session info must not suppress this lock's first acquisition."""
    with _lock_dispatch() as (session, calls):
        session.info["lock"] = True
        for _ in range(5):
            lock_evidence(session)
        assert len(calls) == 1
        assert "hashtext(current_schema())" in calls[0]
        assert "hashtext('evidence_projection')" in calls[0]


@pytest.mark.parametrize("end", ["commit", "rollback", "close"])
def test_new_transaction_on_same_session_reacquires_lock(end: str) -> None:
    """Transaction completion removes identities before a reusable Session starts again."""
    with _lock_dispatch() as (session, calls):
        for count in range(1, 4):
            lock_evidence(session)
            lock_evidence(session)
            assert len(calls) == count
            getattr(session, end)()
            assert session.get_transaction() is None
        assert not session.info


def test_first_lock_inside_rolled_back_savepoint_is_reacquired() -> None:
    """A rolled-back acquiring savepoint cannot leave a marker on the root."""
    with _lock_dispatch() as (session, calls), session.begin():
        nested = session.begin_nested()
        lock_evidence(session)
        lock_evidence(session)
        nested.rollback()
        lock_evidence(session)
        lock_evidence(session)
        assert len(calls) == 2


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_outer_lock_survives_savepoint_end_without_another_sql(end: str) -> None:
    """An ancestor's lock survives either outcome of an unrelated child savepoint."""
    with _lock_dispatch() as (session, calls), session.begin():
        lock_evidence(session)
        nested = session.begin_nested()
        lock_evidence(session)
        getattr(nested, end)()
        lock_evidence(session)
        assert len(calls) == 1


def test_committed_savepoint_promotes_lock_until_its_parent_rolls_back() -> None:
    """Promotion stops at the actual surviving parent, not the Session's root."""
    with _lock_dispatch() as (session, calls), session.begin():
        outer = session.begin_nested()
        inner = session.begin_nested()
        lock_evidence(session)
        inner.commit()
        lock_evidence(session)
        assert len(calls) == 1
        outer.rollback()
        lock_evidence(session)
        assert len(calls) == 2


def test_committed_savepoint_promotes_lock_until_root_ends() -> None:
    """Savepoint release preserves deduplication, but root commit releases the marker."""
    with _lock_dispatch() as (session, calls):
        nested = session.begin_nested()
        lock_evidence(session)
        nested.commit()
        lock_evidence(session)
        assert len(calls) == 1
        session.commit()
        assert not session.info
        lock_evidence(session)
        assert len(calls) == 2


def test_sqlite_does_not_start_transaction_or_mark_lock() -> None:
    """SQLite retains its writer serialization without advisory SQL or transaction markers."""
    engine = create_engine("sqlite://")
    try:
        with Session(engine) as session:
            lock_evidence(session)
            assert session.get_transaction() is None
            assert not session.info
    finally:
        engine.dispose()
