# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mandatory-on-PG advisory lock competition, deduplication and transaction evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.vector_cache import lock_evidence
from tests.pg_evidence_helpers import PgJob, pg_trace, require_postgres

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from datakeel.storage.database import Database

pytestmark = pytest.mark.usefixtures("offline_network")


def _take_and_commit(session: Session) -> None:
    lock_evidence(session)
    session.commit()


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_waiter_proceeds_only_after_independent_holder_ends(
    db: Database, record_property: Callable[[str, object], None], end: str
) -> None:
    """Server wait rows and blocking PIDs prove competition before the holder ends."""
    require_postgres(db)
    with pg_trace(db, record_property) as trace, trace.session("A") as holder:
        lock_evidence(holder)
        trace.owns("A", expected=True)
        waiter = PgJob(trace, "B", _take_and_commit)
        try:
            trace.blocked(waiter, "A")
            assert trace.count("B", "before") == 1
            assert trace.count("B") == 0
            trace.note(f"A:{end}:invoked")
            getattr(holder, end)()
            trace.note(f"A:{end}:returned")
            waiter.result()
            assert waiter.done.is_set()
            assert trace.count("A") == trace.count("B") == 1
            trace.owns("A", expected=False)
            trace.owns("B", expected=False)
            trace.ordered(
                "A:after: SELECT pg_advisory_xact_lock",
                "B:before: SELECT pg_advisory_xact_lock",
                "observer:B:blocked",
                f"A:{end}:invoked",
                "B:after: SELECT pg_advisory_xact_lock",
                "B:completed",
            )
        finally:
            holder.rollback()
            waiter.result()


@pytest.mark.parametrize("end", ["commit", "rollback", "close"])
def test_same_session_deduplicates_then_reacquires_after_each_end(
    db: Database, record_property: Callable[[str, object], None], end: str
) -> None:
    """One pinned backend and reusable Session emit one actual lock SQL per transaction."""
    require_postgres(db)
    with pg_trace(db, record_property) as trace, trace.session("A") as session:
        session.info["unrelated"] = True
        for count in range(1, 4):
            trace.prepare(session, "A")
            for _ in range(5):
                lock_evidence(session)
            assert trace.count("A", "before") == trace.count("A") == count
            trace.owns("A", expected=True)
            trace.note(f"A:transaction-{count}:{end}:invoked")
            getattr(session, end)()
            trace.note(f"A:transaction-{count}:{end}:returned")
            assert session.get_transaction() is None
            assert session.info == {"unrelated": True}
            trace.owns("A", expected=False)
        assert trace.count("A", needle="SELECT pg_backend_pid()") == 4


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_first_lock_in_savepoint_retention_and_root_reacquisition(
    db: Database, record_property: Callable[[str, object], None], end: str
) -> None:
    """Release promotes the real lock; rollback releases it and requires another SQL."""
    require_postgres(db)
    with pg_trace(db, record_property) as trace, trace.session("A") as session:
        nested = session.begin_nested()
        lock_evidence(session)
        lock_evidence(session)
        trace.owns("A", expected=True)
        getattr(nested, end)()
        trace.note(f"A:inner-{end}:returned")
        trace.owns("A", expected=end == "commit")
        lock_evidence(session)
        lock_evidence(session)
        expected = 1 if end == "commit" else 2
        assert trace.count("A", "before") == trace.count("A") == expected
        trace.owns("A", expected=True)
        session.rollback()
        trace.note("A:root-rollback:returned")
        trace.owns("A", expected=False)
        trace.prepare(session, "A")
        lock_evidence(session)
        assert trace.count("A") == expected + 1
        trace.owns("A", expected=True)
        trace.ordered(
            "A:after: SAVEPOINT",
            "A:after: SELECT pg_advisory_xact_lock",
            "A:after: RELEASE" if end == "commit" else "A:after: ROLLBACK TO",
            f"A:inner-{end}:returned",
            "A:root-rollback:returned",
            "A:after: SELECT pg_advisory_xact_lock",
        )


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_root_lock_survives_child_savepoint_without_redundant_sql(
    db: Database, record_property: Callable[[str, object], None], end: str
) -> None:
    """Ending a child never drops or reissues the ancestor's real advisory lock."""
    require_postgres(db)
    with pg_trace(db, record_property) as trace, trace.session("A") as session:
        lock_evidence(session)
        nested = session.begin_nested()
        lock_evidence(session)
        # Materialize the savepoint even though the deduplicated call emitted no SQL.
        trace.prepare(session, "A")
        getattr(nested, end)()
        trace.note(f"A:child-{end}:returned")
        trace.owns("A", expected=True)
        lock_evidence(session)
        assert trace.count("A", "before") == trace.count("A") == 1
        trace.ordered(
            "A:after: SELECT pg_advisory_xact_lock",
            "A:after: SAVEPOINT",
            "A:after: RELEASE" if end == "commit" else "A:after: ROLLBACK TO",
            f"A:child-{end}:returned",
        )


@pytest.mark.parametrize("parent_end", ["commit", "rollback"])
def test_two_savepoint_handoffs_and_parent_rollback_reacquire(
    db: Database, record_property: Callable[[str, object], None], parent_end: str
) -> None:
    """Child release transfers to its actual parent; parent rollback loses that lock."""
    require_postgres(db)
    with pg_trace(db, record_property) as trace, trace.session("A") as session:
        parent = session.begin_nested()
        child = session.begin_nested()
        lock_evidence(session)
        child.commit()
        trace.note("A:child-release:returned")
        lock_evidence(session)
        assert trace.count("A") == 1
        trace.owns("A", expected=True)
        getattr(parent, parent_end)()
        trace.note(f"A:parent-{parent_end}:returned")
        trace.owns("A", expected=parent_end == "commit")
        lock_evidence(session)
        expected = 1 if parent_end == "commit" else 2
        assert trace.count("A", "before") == trace.count("A") == expected
        trace.owns("A", expected=True)
        session.rollback()
        trace.note("A:root-rollback:returned")
        trace.owns("A", expected=False)
        trace.prepare(session, "A")
        lock_evidence(session)
        assert trace.count("A") == expected + 1
        trace.ordered(
            "A:after: SAVEPOINT sa_savepoint_1",
            "A:after: SAVEPOINT sa_savepoint_2",
            "A:after: SELECT pg_advisory_xact_lock",
            "A:after: RELEASE SAVEPOINT sa_savepoint_2",
            "A:child-release:returned",
            f"A:parent-{parent_end}:returned",
            "A:root-rollback:returned",
            "A:after: SELECT pg_advisory_xact_lock",
        )
