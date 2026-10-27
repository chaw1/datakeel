# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality jobs execute local generated sources through the ordinary worker."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.dq_models import DqParameters
from datakeel.storage.database import Database, ShardRow, VersionRow
from datakeel.storage.dq_jobs import schedule_rule
from datakeel.storage.dq_reads import get_run, read_issues, read_results
from datakeel.storage.dq_rows import DqRunRow
from datakeel.storage.dq_store import upsert_rule
from datakeel.worker.dq_runner import execute_dq
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker
from tests.storage.test_dq_store import definition

if TYPE_CHECKING:
    from pathlib import Path


def _source(db: Database, tmp_path: Path, source_id: str = "sample") -> Path:
    path = tmp_path / "business.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE orders(amount REAL); INSERT INTO orders VALUES(NULL),(3)"
        )
    import_catalog(
        db,
        CatalogImportRequest(
            source_id=source_id, name="Example orders", connection_url=f"sqlite:///{path}"
        ),
    )
    return path


def _enqueue(db: Database, key: str) -> str:
    with db.session() as session:
        run = schedule_rule(session, "orders-required", key)
        session.commit()
    return run.id


def test_worker_persists_redacted_failures_and_recovery(db: Database, tmp_path: Path) -> None:
    """Actual source scans produce incidents and then recover without new data versions."""
    source = _source(db, tmp_path)
    with db.session() as session:
        upsert_rule(session, definition(), None, "reviewer")
        session.commit()
    _enqueue(db, "first")
    run_worker(db, once=True)
    failed = read_results(db, "orders-required")[0]
    assert failed.status == "failed"
    assert failed.samples[0].value == "[REDACTED]"
    assert read_issues(db)[0].status == "open"
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE orders SET amount=1 WHERE amount IS NULL")
    _enqueue(db, "second")
    run_worker(db, once=True)
    assert read_results(db, "orders-required")[0].status == "passed"
    assert read_issues(db)[0].status == "recovered"
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 1


def test_worker_cold_start_accumulates_successful_baselines(db: Database, tmp_path: Path) -> None:
    """Insufficient baseline observations count toward the later valid baseline."""
    _source(db, tmp_path)
    rule = definition().model_copy(
        update={
            "kind": "volume_change",
            "params": DqParameters(baseline_runs=2),
        }
    )
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        session.commit()
    for index in range(3):
        _enqueue(db, str(index))
        run_worker(db, once=True)
    assert [result.status for result in read_results(db, rule.id)] == [
        "passed",
        "baseline_insufficient",
        "baseline_insufficient",
    ]


def test_worker_missing_source_records_job_failure(db: Database) -> None:
    """An unavailable catalog source leaves a durable failure instead of killing the worker."""
    with db.session() as session:
        upsert_rule(session, definition(), None, "reviewer")
        session.commit()
    identifier = _enqueue(db, "unavailable")
    run_worker(db, once=True)
    with db.session() as session:
        run = get_run(session, identifier)
        assert run.state == "COMPLETED"
        assert read_results(db, "orders-required")[0].status == "error"
        assert read_issues(db)[0].status == "open"


def test_worker_missing_run_and_reaper_exhaustion_are_terminal(db: Database) -> None:
    """Broken frozen job links and expired final attempts use existing terminal handling."""
    with db.session() as session:
        upsert_rule(session, definition(), None, "reviewer")
        session.commit()
    identifier = _enqueue(db, "broken")
    queue = DatabaseQueue(db, max_attempts=1)
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        row = session.get(DqRunRow, identifier)
        assert row is not None
        session.delete(row)
        session.commit()
    assert execute_dq(queue, lease)
    final_id = _enqueue(db, "expired")
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    with db.session() as session:
        assert get_run(session, final_id).state == "FAILED"


def test_worker_resolves_escaped_source_identity(db: Database, tmp_path: Path) -> None:
    """Raw source names containing delimiters map to their catalog asset identities."""
    identifier = "branch/warehouse name"
    _source(db, tmp_path, identifier)
    base = definition()
    rule = base.model_copy(
        update={
            "target": base.target.model_copy(
                update={"source_id": identifier},
            )
        }
    )
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        session.commit()
    _enqueue(db, "escaped-source")
    run_worker(db, once=True)
    assert read_results(db, rule.id)[0].status == "failed"
    assert read_results(db, rule.id)[0].message == ""
