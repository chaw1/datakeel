# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Task finish times track durable terminal transitions without fabricating legacy history."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import ShardRow
from datakeel.storage.task_queries import query_task
from datakeel.worker.queue import DatabaseQueue
from tests.worker.test_queue import seed

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_success_records_finish_time_only_after_last_shard(db: Database, tmp_path: Path) -> None:
    """Partial progress has no finish time; a stale completion cannot change the final time."""
    queue = DatabaseQueue(db)
    task_id = queue.submit(seed(db, tmp_path), "finish-success", shards=2)
    first = queue.claim()
    assert first is not None
    assert query_task(db, task_id).finished_at is None
    assert queue.finish(first, [], [])
    assert query_task(db, task_id).finished_at is None
    second = queue.claim()
    assert second is not None
    assert queue.finish(second, [], [])
    completed = query_task(db, task_id)
    assert completed.finished_at is not None
    assert completed.finished_at >= completed.created_at
    assert not queue.finish(second, [], [])
    assert not queue.cancel(task_id)
    assert query_task(db, task_id).finished_at == completed.finished_at


def test_failure_records_time_and_fences_sibling_completion(db: Database, tmp_path: Path) -> None:
    """Failure stamps one task finish time while cancelling unfinished sibling shards."""
    queue = DatabaseQueue(db)
    task_id = queue.submit(seed(db, tmp_path), "finish-failure", shards=2)
    first, second = queue.claim(), queue.claim()
    assert first is not None
    assert second is not None
    assert queue.finish(first, [], [], error="Synthetic operator failure")
    failed = query_task(db, task_id)
    assert failed.state == "FAILED"
    assert failed.finished_at is not None
    assert failed.finished_at >= failed.created_at
    assert not queue.finish(second, [], [])
    assert not queue.cancel(task_id)
    assert query_task(db, task_id).finished_at == failed.finished_at


@pytest.mark.parametrize("claim_first", [False, True])
def test_cancellation_records_stable_time_and_fences_leases(
    db: Database, tmp_path: Path, *, claim_first: bool
) -> None:
    """Cancelling queued or running work is idempotent and forbids later publication."""
    queue = DatabaseQueue(db)
    task_id = queue.submit(seed(db, tmp_path), "finish-cancel", shards=2)
    lease = queue.claim() if claim_first else None
    assert queue.cancel(task_id)
    cancelled = query_task(db, task_id)
    assert cancelled.state == "CANCELLED"
    assert cancelled.finished_at is not None
    assert cancelled.finished_at >= cancelled.created_at
    assert not queue.cancel(task_id)
    assert query_task(db, task_id).finished_at == cancelled.finished_at
    assert queue.claim() is None
    if lease is not None:
        assert not queue.heartbeat(lease)
        assert not queue.finish(lease, [], [])
    with db.session() as session:
        shards = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task_id)))
        assert all(shard.state == "CANCELLED" and shard.lease_owner is None for shard in shards)
    assert queue.relay() == 1
    assert queue.relay() == 0


def test_cancel_missing_task_reports_not_found(db: Database) -> None:
    """An unknown task identifier cannot create a cancellation record."""
    with pytest.raises(NotFoundError, match="Task not found"):
        DatabaseQueue(db).cancel("missing")
