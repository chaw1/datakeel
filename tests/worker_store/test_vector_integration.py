# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Joint vector/typed completion transaction and retry-policy regressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, select

from datakeel.actions.worker import reconcile_runs
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.datasets import materialize_files
from datakeel.evidence.vector_execution import VectorExecution
from datakeel.persistence.task_completion import BoundTaskCompletion
from datakeel.persistence.task_queries import query_task
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.pipeline import run_pipeline
from datakeel.storage.action_rows import ApprovalRow
from datakeel.storage.vector_budget import dispatch_vector, list_vector_attempts, reserve_vector
from datakeel.storage.vector_rows import VectorAccountRow
from datakeel.worker_store.rows import OutboxRow, ShardRow, TaskRow
from tests.evidence.vector_helpers import leased_vector, vector_dataset, vector_pipeline
from tests.worker_store.test_completion_transactions import action_state, facts

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.engine import Connection

    from datakeel.core.evidence_execution import PendingExtraction
    from datakeel.core.models import FileItem
    from datakeel.storage.database import Database
    from datakeel.worker_store.completion import CompletionRequest
    from datakeel.worker_store.task_queue import Lease


def pending_vectors(
    db: Database, directory: Path
) -> tuple[Lease, list[FileItem], tuple[PendingExtraction, ...]]:
    """Produce actual fake products without committing their pending publication."""
    lease, permit, _, _ = leased_vector(db, directory / "inputs")
    execution = VectorExecution(
        db,
        EvidenceExecutionContext(
            task_id=lease.task_id,
            shard_id=lease.shard_id,
            version_id=lease.input_version_id or "missing",
        ),
        permit,
    )
    outputs = run_pipeline(
        materialize_files(lease.inputs),
        directory / "outputs",
        lease.pipeline,
        operator_executor=execution.execute_node,
    )
    assert len(execution.pending) == 2
    return lease, outputs, tuple(execution.pending)


def transition(queue: DatabaseQueue, lease: Lease, mode: str) -> None:
    """Use the real failure, cancellation or reaper entry without dispatching again."""
    if mode == "cancel":
        assert queue.cancel(lease.task_id)
    elif mode == "failure":
        assert queue.finish(lease, lease.inputs, [], error="vector_generated_failure")
    else:
        assert queue.reap() == 1


def recovery_failure(
    lease: Lease,
) -> tuple[list[str], Callable[[BoundTaskCompletion, CompletionRequest], None]]:
    """Observe flushed terminal/outbox, then fail after a real recovery SQL write."""
    recover = BoundTaskCompletion.recover
    phases: list[str] = []

    def fail_after_recovery(port: BoundTaskCompletion, request: CompletionRequest) -> None:
        session = port._session  # noqa: SLF001  # Observe the transaction-bound adapter.
        assert not any(isinstance(row, OutboxRow) for row in session.new)
        task = session.get(TaskRow, lease.task_id)
        assert task is not None
        assert task.state in {"FAILED", "CANCELLED"}
        assert (
            session.scalar(
                select(OutboxRow).where(
                    OutboxRow.idempotency_key == f"task:{lease.task_id}:terminal"
                )
            )
            is not None
        )
        phases.append(request.phase)
        recover(port, request)
        session.flush()
        msg = "Generated failure after recovery write"
        raise RuntimeError(msg)

    return phases, fail_after_recovery


@pytest.mark.parametrize("mode", ["failure", "cancel", "reap"])
@pytest.mark.parametrize("sent", [False, True])
def test_vector_recovery_is_post_outbox_atomic_and_never_resends(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, *, sent: bool
) -> None:
    """A recovery second-write failure rolls back fencing/outbox/refund, then retries once."""
    lease, permit, node, wire = leased_vector(db, tmp_path)
    reserve = reserve_vector(db, permit, node.node_id, wire.frozen)
    if sent:
        dispatch_vector(db, permit, reserve.id, wire.frozen)
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = shard.lease_expires_at = 0
        session.commit()
    before = facts(db)
    queue = DatabaseQueue(db, max_attempts=99)
    phases, fail_after_recovery = recovery_failure(lease)

    with monkeypatch.context() as patch:
        patch.setattr(BoundTaskCompletion, "recover", fail_after_recovery)
        with pytest.raises(RuntimeError, match="after recovery write"):
            transition(queue, lease, mode)
    assert phases == ["CANCELLED" if mode == "cancel" else "FAILED"]
    assert facts(db) == before
    transition(queue, lease, mode)
    assert list_vector_attempts(db, lease.task_id)[0].state == ("UNKNOWN" if sent else "REFUNDED")
    with db.session() as session:
        account = session.get(VectorAccountRow, permit.plan_id)
        shard = session.get(ShardRow, lease.shard_id)
        assert account is not None
        assert shard is not None
        assert (account.requests, account.cost_nanos) == (
            int(sent),
            wire.frozen.token_bound if sent else 0,
        )
        assert shard.outputs == []
    assert queue.reap() == 0
    assert queue.claim() is None
    assert not queue.finish(lease, [], [])
    assert not queue.cancel(lease.task_id)
    view = query_task(db, lease.task_id)
    assert view.vector is not None
    assert view.vector.nodes == ()
    assert view.error == (
        "vector_lease_expired_outcome_unknown"
        if mode == "reap"
        else "vector_generated_failure"
        if mode == "failure"
        else None
    )
    assert action_state(db, lease.task_id) == ("QUEUED", 0)
    assert reconcile_runs(db) == 1
    assert reconcile_runs(db) == 0
    assert action_state(db, lease.task_id) == ("FAILED", 1)


def test_vector_products_roll_back_after_outbox_then_publish_and_receipt_once(
    db: Database, tmp_path: Path
) -> None:
    """Vector caches/evidence, business tables and ledger roll back together on a late SQL fault."""
    lease, outputs, payload = pending_vectors(db, tmp_path)
    queue = DatabaseQueue(db)
    before = facts(db)
    assert len(before) == (103 if db.sqlite else 102)
    inserts: list[str] = []

    def fail_after_outbox(
        _connection: Connection, _cursor: object, statement: str, *_args: object
    ) -> None:
        if statement.startswith("INSERT INTO outbox"):
            inserts.append(statement)
            msg = "Generated post-outbox failure"
            raise RuntimeError(msg)

    event.listen(db.engine, "after_cursor_execute", fail_after_outbox)
    try:
        with pytest.raises(RuntimeError, match="post-outbox failure"):
            queue.finish(lease, outputs, [], evidence=payload)
    finally:
        event.remove(db.engine, "after_cursor_execute", fail_after_outbox)
    assert inserts
    assert facts(db) == before
    assert queue.finish(lease, outputs, [], evidence=payload)
    assert not queue.finish(lease, outputs, [], evidence=payload)
    view = query_task(db, lease.task_id)
    assert view.vector is not None
    assert view.vector.status == "success"
    assert action_state(db, lease.task_id) == ("QUEUED", 0)
    assert reconcile_runs(db) == 1
    assert reconcile_runs(db) == 0
    assert action_state(db, lease.task_id) == ("SUCCEEDED", 1)
    assert queue.relay() == 2
    assert queue.relay() == 0


@pytest.mark.parametrize("defect", ["approval", "missing-node", "missing-samples"])
def test_vector_success_requires_human_approval_and_every_pending_product(
    db: Database, tmp_path: Path, defect: str
) -> None:
    """Publication rechecks consumed approval and whole-DAG products behind the lease fence."""
    lease, outputs, payload = pending_vectors(db, tmp_path)
    if defect == "approval":
        with db.session() as session:
            approval = session.scalars(select(ApprovalRow)).one()
            approval.consumed = False
            session.commit()
    elif defect == "missing-node":
        payload = payload[:1]
    else:
        payload = (
            payload[0].model_copy(
                update={"bundle": payload[0].bundle.model_copy(update={"vector_samples": ()})}
            ),
            *payload[1:],
        )
    before = facts(db)
    with pytest.raises(
        VectorError,
        match=r"approval_or_lease_invalid|publication_incomplete|bundle_integrity_invalid",
    ):
        DatabaseQueue(db).finish(lease, outputs, [], evidence=payload)
    assert facts(db) == before


def test_vector_attempt_identity_survives_removed_dag_and_ordinary_leases_retry(
    db: Database, tmp_path: Path
) -> None:
    """Attempts prevent retry even without a DAG; ordinary leases requeue until their cap."""
    lease, permit, node, wire = leased_vector(db, tmp_path / "vector")
    attempt = reserve_vector(db, permit, node.node_id, wire.frozen)
    dispatch_vector(db, permit, attempt.id, wire.frozen)
    with db.session() as session:
        task = session.get(TaskRow, lease.task_id)
        shard = session.get(ShardRow, lease.shard_id)
        assert task is not None
        assert shard is not None
        task.pipeline = None
        shard.heartbeat_at = 0
        session.commit()
    queue = DatabaseQueue(db, max_attempts=2)
    assert queue.reap() == 1
    assert query_task(db, lease.task_id).error == "vector_lease_expired_outcome_unknown"
    assert list_vector_attempts(db, lease.task_id)[0].state == "UNKNOWN"


def test_ordinary_leases_refresh_expiry_and_retry_until_max_attempts(
    db: Database, tmp_path: Path
) -> None:
    """Ordinary attempts keep heartbeat expiry and retry policy independent of vectors."""
    queue = DatabaseQueue(db, max_attempts=2)
    dataset = vector_dataset(db, tmp_path / "ordinary")
    task_id = queue.submit(dataset, "ordinary")
    first = queue.claim()
    assert first is not None
    assert first.task_id == task_id
    assert queue.heartbeat(first)
    with db.session() as session:
        shard = session.get(ShardRow, first.shard_id)
        assert shard is not None
        assert shard.lease_expires_at is not None
        assert shard.heartbeat_at is not None
        assert shard.lease_expires_at == shard.heartbeat_at + queue.lease_seconds
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    assert query_task(db, task_id).state == "QUEUED"
    second = queue.claim()
    assert second is not None
    assert second.owner != first.owner
    assert not queue.finish(first, [], [])
    with db.session() as session:
        shard = session.get(ShardRow, second.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    assert query_task(db, task_id).error == "Worker lease expired after maximum retries"


@pytest.mark.parametrize("as_dict", [False, True])
def test_direct_vector_submission_refuses_before_database_or_idempotency_lookup(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, as_dict: bool
) -> None:
    """The original submit entry refuses vectors even for missing datasets or existing keys."""
    dataset = vector_dataset(db, tmp_path)
    queue = DatabaseQueue(db)
    queue.submit(dataset, "existing")
    pipeline = vector_pipeline()

    def forbid_session() -> None:
        pytest.fail("Direct vector submission entered the database")

    monkeypatch.setattr(db, "session", forbid_session)
    for dataset_id in (dataset, "missing"):
        with pytest.raises(VectorError, match="vector_direct_queue_refused"):
            queue.submit(dataset_id, "existing", pipeline.model_dump() if as_dict else pipeline)
