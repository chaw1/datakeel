# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Completion, terminal outbox and later action receipts retain distinct atomic owners."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import MetaData, Table, event, inspect, select

from datakeel.actions.worker import reconcile_runs
from datakeel.core.errors import ConflictError
from datakeel.dataset_store.rows import VersionRow
from datakeel.persistence.task_completion import BoundTaskCompletion
from datakeel.storage.action_rows import ActionAuditRow, ActionRunRow
from datakeel.storage.datasheet_jobs import get_job as datasheet_job
from datakeel.storage.dq_reads import get_run as dq_run
from datakeel.storage.kg_store import get_job as kg_job
from datakeel.worker_store.rows import OutboxRow, ShardRow, TaskRow
from datakeel.worker_store.task_queries import query_task
from tests.worker_store.completion_fixtures import enqueue

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Session

    from datakeel.storage.database import Database

KINDS = ("pipeline", "kg", "dq", "datasheet")


def facts(db: Database) -> dict[str, list[str]]:
    """Fingerprint every generated table after claim, including JSON and audit payloads."""
    with db.engine.connect() as connection:
        return {
            table: sorted(
                json.dumps(tuple(row), default=str)
                for row in connection.execute(
                    select(Table(table, MetaData(), autoload_with=connection))
                )
            )
            for table in inspect(connection).get_table_names()
        }


def action_state(db: Database, task_id: str) -> tuple[str, int]:
    """Observe the asynchronous action and count only its worker-phase audits."""
    with db.session() as session:
        row = session.scalars(select(ActionRunRow).where(ActionRunRow.task_id == task_id)).one()
        audits = list(
            session.scalars(select(ActionAuditRow).where(ActionAuditRow.phase == "WORKER"))
        )
        return row.status, len(audits)


@pytest.mark.parametrize("kind", KINDS)
def test_second_write_failure_rolls_back_all_facts_and_retry_receipts_once(
    db: Database,
    tmp_path: Path,
    kind: str,
) -> None:
    """An actual post-outbox SQL failure leaves every pre-attempt fact intact and retryable."""
    queue, lease, payload = enqueue(db, tmp_path, kind)
    before = facts(db)
    commits: list[bool] = []
    injected: list[str] = []

    def fail_after_outbox(
        _connection: Connection, _cursor: object, statement: str, *_args: object
    ) -> None:
        if statement.startswith("INSERT INTO outbox"):
            injected.append(statement)
            msg = "Generated failure after terminal outbox write"
            raise RuntimeError(msg)

    def committed(_connection: Connection) -> None:
        commits.append(True)

    event.listen(db.engine, "after_cursor_execute", fail_after_outbox)
    event.listen(db.engine, "commit", committed)
    try:
        with pytest.raises(RuntimeError, match="after terminal outbox"):
            queue.finish(lease, lease.inputs, [], evidence=payload)
        assert injected
        assert commits == []
        assert facts(db) == before
    finally:
        event.remove(db.engine, "after_cursor_execute", fail_after_outbox)
    try:
        assert queue.finish(lease, lease.inputs, [], evidence=payload)
        assert commits == [True]
    finally:
        event.remove(db.engine, "commit", committed)
    assert action_state(db, lease.task_id) == ("QUEUED", 0)
    assert not queue.finish(lease, [], [], evidence=payload)
    assert not queue.cancel(lease.task_id)
    assert reconcile_runs(db) == 1
    assert reconcile_runs(db) == 0
    assert action_state(db, lease.task_id) == ("SUCCEEDED", 1)
    assert queue.relay() == 2  # Task terminal plus the subsequent action receipt.
    assert queue.relay() == 0
    with db.session() as session:
        versions = list(
            session.scalars(select(VersionRow).where(VersionRow.task_id == lease.task_id))
        )
        assert len(versions) == (1 if kind == "pipeline" else 0)


def assert_domain_failure(db: Database, kind: str, task_id: str, *, cancelled: bool) -> None:
    """Read back the real domain outcome instead of relying on queue state alone."""
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        if kind == "kg":
            run = kg_job(db, task.kg_run_id or "").run
            assert run.status == "failed"
            assert run.report.error == (task.error or "Graph task cancelled")
        elif kind == "dq":
            run = dq_run(session, task.dq_run_id or "")
            assert run.state == ("CANCELLED" if cancelled else "FAILED")
            assert (run.result_id is None) == cancelled
            assert run.error == (task.error or "Quality task cancelled")
        elif kind == "datasheet":
            job = datasheet_job(db, task.datasheet_job_id or "")
            assert job.status == ("CANCELLED" if cancelled else "FAILED")
            assert job.error == (task.error or "Datasheet task cancelled")
        assert not session.scalar(select(VersionRow.id).where(VersionRow.task_id == task_id))


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("mode", ["failure", "cancel", "exhausted"])
def test_failure_cancel_and_exhaustion_publish_once_then_reconcile(
    db: Database,
    tmp_path: Path,
    kind: str,
    mode: str,
) -> None:
    """Domain failure, terminal attribution and the later failed action receipt agree."""
    queue, lease, payload = enqueue(db, tmp_path, kind)
    if mode == "cancel":
        assert queue.cancel(lease.task_id)
    elif mode == "failure":
        assert queue.finish(lease, [], [], error="Generated failure")
    else:
        with db.session() as session:
            shard = session.get(ShardRow, lease.shard_id)
            assert shard is not None
            shard.heartbeat_at = 0
            session.commit()
        assert queue.reap() == 1
        assert queue.reap() == 0
    finished = query_task(db, lease.task_id)
    assert finished.state == ("CANCELLED" if mode == "cancel" else "FAILED")
    assert finished.finished_at is not None
    assert_domain_failure(db, kind, lease.task_id, cancelled=mode == "cancel")
    assert action_state(db, lease.task_id) == ("QUEUED", 0)
    assert not queue.finish(lease, [], [], evidence=payload)
    assert not queue.heartbeat(lease)
    assert not queue.cancel(lease.task_id)
    assert query_task(db, lease.task_id).finished_at == finished.finished_at
    with db.session() as session:
        terminal = session.scalars(
            select(OutboxRow).where(OutboxRow.idempotency_key == f"task:{lease.task_id}:terminal")
        ).one()
        assert terminal.payload["operator"] == f"{kind}.complete"
        assert terminal.payload["source_module"] == "worker"
        assert terminal.payload["run_state"] == finished.state
    assert reconcile_runs(db) == 1
    assert reconcile_runs(db) == 0
    assert action_state(db, lease.task_id) == ("FAILED", 1)
    assert queue.relay() == 2
    assert queue.relay() == 0


@pytest.mark.parametrize("operation", ["finish", "cancel", "reap"])
def test_ambiguous_task_rejection_rolls_back_every_transition(
    db: Database,
    tmp_path: Path,
    operation: str,
) -> None:
    """Even failure/cancel/reaper cannot publish for a task linked to multiple domains."""
    queue, lease, _payload = enqueue(db, tmp_path, "kg")
    with db.session() as session:
        task = session.get(TaskRow, lease.task_id)
        shard = session.get(ShardRow, lease.shard_id)
        assert task is not None
        assert shard is not None
        task.dq_run_id = "ambiguous"
        shard.heartbeat_at = 0
        session.commit()
    before = facts(db)
    rejected = False
    try:
        if operation == "finish":
            queue.finish(lease, [], [], error="Generated failure")
        elif operation == "cancel":
            queue.cancel(lease.task_id)
        else:
            queue.reap()
    except ConflictError:
        rejected = True
    assert rejected
    assert facts(db) == before


def test_refreshed_heartbeat_blocks_exhaustion_without_entering_completion(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finish-time cutoff fence wins over a reaper's previously collected lease."""
    queue, lease, _payload = enqueue(db, tmp_path, "pipeline")
    assert queue.heartbeat(lease)
    before = facts(db)
    entered: list[bool] = []

    def record(session: Session) -> BoundTaskCompletion:
        entered.append(True)
        return BoundTaskCompletion(session)

    monkeypatch.setattr(queue, "_completion_factory", record)
    assert not queue.finish(lease, [], [], error="Expired", expired_before=0)
    assert entered == []
    assert facts(db) == before
