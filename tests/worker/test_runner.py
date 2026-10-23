# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Failure durability and stale lease regression checks for shard execution."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Never

import pytest
from sqlalchemy import select

from datakeel.core.errors import ExecutionError
from datakeel.storage.database import Database, TaskRow
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import _pulse, execute, run_worker
from tests.worker.test_queue import seed

if TYPE_CHECKING:
    from pathlib import Path


def fail_pipeline(*_args: object, **_kwargs: object) -> Never:
    """Provide the fail pipeline test fixture."""
    msg = "generated fixture failure"
    raise OSError(msg)


def test_execute_operator_failure_persists_failed_task(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify execute operator failure persists failed task."""
    queue = DatabaseQueue(db)
    task_id = queue.submit(seed(db, tmp_path), "failed-execution")
    lease = queue.claim()
    monkeypatch.setattr("datakeel.worker.runner.run_pipeline", fail_pipeline)
    assert execute(queue, lease)
    with db.session() as session:
        task = session.scalar(select(TaskRow).where(TaskRow.id == task_id))
        assert task.state == "FAILED"
        assert "OSError" in task.error
    assert queue.relay() == 1


def test_execute_failure_without_lease_raises_instead_of_silently_discarding(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify execute failure without lease raises instead of silently discarding."""
    queue = DatabaseQueue(db)
    queue.submit(seed(db, tmp_path), "lost-lease")
    lease = queue.claim()
    assert queue.finish(lease, [], [])
    monkeypatch.setattr("datakeel.worker.runner.run_pipeline", fail_pipeline)
    with pytest.raises(ExecutionError, match="Cannot persist shard failure"):
        execute(queue, lease)


def test_heartbeat_stops_when_ownership_was_lost(db: Database, tmp_path: Path) -> None:
    """Verify heartbeat stops when ownership was lost."""
    queue = DatabaseQueue(db, lease_seconds=0.01)
    queue.submit(seed(db, tmp_path), "heartbeat-lost")
    lease = queue.claim()
    assert queue.finish(lease, [], [])
    _pulse(queue, lease, threading.Event())


def test_worker_waits_when_queue_is_empty(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify worker waits when queue is empty."""

    def stop_polling(_delay: float) -> Never:
        """Provide the stop polling test fixture."""
        msg = "test loop boundary"
        raise InterruptedError(msg)

    monkeypatch.setattr("datakeel.worker.runner.time.sleep", stop_polling)
    with pytest.raises(InterruptedError, match="test loop boundary"):
        run_worker(db)
