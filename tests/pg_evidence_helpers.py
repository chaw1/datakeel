# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Observe real fixture PostgreSQL locks without replacing any production SQL."""

from __future__ import annotations

import json
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from sqlalchemy.engine import Connection

    from datakeel.storage.database import Database

_LOCKS = """
SELECT pid, granted FROM pg_locks
WHERE locktype = 'advisory'
  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND classid = (hashtext(current_schema())::bigint & 4294967295)::oid
  AND objid = (hashtext('evidence_projection')::bigint & 4294967295)::oid
  AND objsubid = 2
ORDER BY pid, granted
"""
_TIMEOUT = 15
_LABEL = "test.pg_evidence.label"


def require_postgres(db: Database) -> None:
    """Skip only SQLite; the normal PG CI shard executes every case without opt-in."""
    if db.sqlite:
        pytest.skip("Real PostgreSQL advisory-lock evidence; SQLite cannot execute this test")
    assert db.engine.dialect.name == "postgresql"
    assert db.engine.url.host in {"localhost", "127.0.0.1"}


@dataclass
class LockGate:
    """Pause immediately before the first actual advisory SQL, solely for scheduling."""

    entered: Event = field(default_factory=Event)
    resume: Event = field(default_factory=Event)


class PgTrace:
    """Keep ordered SQL dispatch/completion and server observations in JUnit properties."""

    def __init__(self, db: Database) -> None:
        """Observe only labeled connections in this test's private fixture database."""
        self.db = db
        self.entries: list[str] = []
        self.sql: list[tuple[str, str, str]] = []
        self.pids: dict[str, int] = {}
        self.gates: dict[str, LockGate] = {}
        self._mutex = Lock()

    def note(self, entry: str) -> None:
        """Append one event atomically so worker and observer share a total order."""
        with self._mutex:
            self.entries.append(entry)

    def _capture(self, connection: Connection, phase: str, statement: str) -> None:
        label = connection.info.get(_LABEL)
        if not isinstance(label, str):
            return
        with self._mutex:
            self.sql.append((label, phase, statement))
            self.entries.append(f"{label}:{phase}: {statement}")
        gate = self.gates.get(label)
        if phase == "before" and "pg_advisory_xact_lock" in statement and gate is not None:
            self.gates.pop(label)
            gate.entered.set()
            assert gate.resume.wait(_TIMEOUT), "scheduler did not release the lock SQL gate"

    def before(
        self,
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy event signature.
    ) -> None:
        """Record SQL before sending it, without modifying text or parameters."""
        self._capture(connection, "before", statement)

    def after(
        self,
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy event signature.
    ) -> None:
        """Record successful cursor completion, including actual lock grant."""
        self._capture(connection, "after", statement)

    def commit(self, connection: Connection) -> None:
        """Record commit dispatch; explicit caller markers record its completion."""
        self._capture(connection, "transaction", "COMMIT")

    def rollback(self, connection: Connection) -> None:
        """Record rollback dispatch; explicit caller markers record its completion."""
        self._capture(connection, "transaction", "ROLLBACK")

    def prepare(self, session: Session, label: str) -> int:
        """Identify the real backend and bound failure cleanup with server timeouts."""
        session.connection().info[_LABEL] = label
        pid = session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        assert self.pids.setdefault(label, pid) == pid
        session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
        session.execute(text("SET LOCAL lock_timeout = '12000ms'"))
        self.note(f"{label}:ready pid={pid}")
        return pid

    @contextmanager
    def session(self, label: str) -> Generator[Session]:
        """Pin a Session to one checked-out connection, including reuse after close."""
        with self.db.engine.connect() as connection:
            try:
                with Session(connection, expire_on_commit=False) as session:
                    self.prepare(session, label)
                    yield session
            finally:
                connection.info.pop(_LABEL, None)

    def count(self, label: str, phase: str = "after", needle: str = "pg_advisory_xact_lock") -> int:
        """Count completed or dispatched matching real statements for one backend."""
        return sum(
            owner == label and step == phase and needle in sql for owner, step, sql in self.sql
        )

    def ordered(self, *tokens: str) -> None:
        """Require each unambiguous marker to occur strictly after the previous one."""
        position = -1
        for token in tokens:
            position = next(
                index
                for index, entry in enumerate(self.entries)
                if index > position and token in entry
            )

    def locks(self) -> list[tuple[int, bool]]:
        """Read only this database/schema's two-key projection advisory lock."""
        with self.db.engine.connect() as connection:
            return [(int(pid), bool(granted)) for pid, granted in connection.execute(text(_LOCKS))]

    def owns(self, label: str, *, expected: bool) -> None:
        """Observe lock retention/release synchronously after a transaction operation."""
        locks = self.locks()
        self.note(f"observer:{label}:owns={expected} pg_locks={locks}")
        assert ((self.pids[label], True) in locks) is expected

    def blocked(self, waiter: PgJob, holder: str) -> None:
        """Poll server state to a deadline; elapsed time is never evidence of blocking."""
        assert waiter.ready.wait(_TIMEOUT), "worker did not initialize its independent connection"
        deadline = monotonic() + _TIMEOUT
        with self.db.engine.connect() as observer:
            while monotonic() < deadline:
                if waiter.done.is_set():
                    waiter.result()
                    pytest.fail("waiter completed before holder released the lock")
                locks = self.locks()
                if (self.pids[waiter.label], False) not in locks:
                    continue
                blockers = observer.scalar(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": self.pids[waiter.label]}
                )
                assert isinstance(blockers, list)
                assert self.pids[holder] in blockers
                assert not waiter.done.is_set()
                assert (self.pids[holder], True) in locks
                assert self.pids[holder] != self.pids[waiter.label]
                self.note(f"observer:{waiter.label}:blocked pg_locks={locks} blockers={blockers}")
                return
        pytest.fail("server did not report the expected advisory-lock waiter")


def source_fingerprints() -> dict[str, str]:
    """Bind each runtime trace to the production and regression sources actually read."""
    root = Path(__file__).resolve().parents[1]
    paths = (
        "datakeel/storage/vector_cache.py",
        "datakeel/storage/evidence_store.py",
        "datakeel/storage/evidence_decisions.py",
        "datakeel/storage/evidence_projection.py",
        "tests/pg_evidence_helpers.py",
        "tests/evidence/pg_fixtures.py",
        "tests/storage/test_evidence_locks_pg.py",
        "tests/evidence/test_vector_publication_pg.py",
    )
    return {name: sha256((root / name).read_bytes()).hexdigest() for name in paths}


@contextmanager
def pg_trace(db: Database, record_property: Callable[[str, object], None]) -> Generator[PgTrace]:
    """Attach read-only SQL observers and export evidence even when assertions fail."""
    trace = PgTrace(db)
    record_property("pg_lock_sources", json.dumps(source_fingerprints(), sort_keys=True))
    stack_sql = (
        "SELECT current_database(), current_schema(), "
        "current_setting('server_version'), current_setting('transaction_isolation')"
    )
    with db.engine.connect() as connection:
        stack = tuple(connection.execute(text(stack_sql)).one())
    trace.note(f"observer:stack SQL={stack_sql} result={stack}")
    record_property("pg_lock_stack", json.dumps(stack))
    listeners = (
        ("before_cursor_execute", trace.before),
        ("after_cursor_execute", trace.after),
        ("commit", trace.commit),
        ("rollback", trace.rollback),
    )
    for name, listener in listeners:
        event.listen(db.engine, name, listener)
    try:
        yield trace
    finally:
        for name, listener in listeners:
            event.remove(db.engine, name, listener)
        record_property("pg_lock_trace", json.dumps(trace.entries))
        record_property("pg_lock_observer_sql", _LOCKS)
        record_property("pg_lock_pids", json.dumps(trace.pids, sort_keys=True))


class PgJob:
    """Run a real operation on a separate connection and propagate all worker failures."""

    def __init__(self, trace: PgTrace, label: str, operation: Callable[[Session], object]) -> None:
        """Start a bounded worker; its Session is created and used only in that thread."""
        self.label = label
        self.ready = Event()
        self.done = Event()
        self._future: Future[object] = Future()
        self._thread = Thread(target=self._run, args=(trace, operation), daemon=True)
        self._thread.start()

    def _run(self, trace: PgTrace, operation: Callable[[Session], object]) -> None:
        try:
            with trace.session(self.label) as session:
                self.ready.set()
                result = operation(session)
            trace.note(f"{self.label}:completed")
            self._future.set_result(result)
        except BaseException as error:  # noqa: BLE001  # Forward even pytest outcomes to the owner.
            self._future.set_exception(error)
        finally:
            self.done.set()

    def result(self) -> object:
        """Require completion and join the worker so fixture teardown cannot race it."""
        try:
            return self._future.result(timeout=_TIMEOUT + 2)
        finally:
            self._thread.join(timeout=_TIMEOUT + 2)
            assert not self._thread.is_alive(), "PG worker outlived its server-side timeout"
