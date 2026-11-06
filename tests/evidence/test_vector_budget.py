# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""W-E-A3: atomic fake budgets, predispatch durability and conservative recovery."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from datakeel.core.models import utcnow
from datakeel.core.vector_models import VectorError
from datakeel.evidence.vector_transport import FakeReply, FakeVectorTransport
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queries import query_task
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.storage.vector_budget import list_vector_attempts, reserve_vector
from datakeel.storage.vector_rows import VectorAccountRow, VectorCacheRow
from datakeel.worker_store.rows import ShardRow
from tests.db_templates import restart_database
from tests.evidence.vector_helpers import leased_vector, vector_dataset, vector_run

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.vector_models import FrozenVectorNode
    from datakeel.evidence.vector_payload import PreparedWire
    from datakeel.storage.database import Database


def test_concurrent_duplicate_reservation_is_atomic_and_durable(
    db: Database, tmp_path: Path
) -> None:
    """Four racing workers can occupy only one attempt for the same approved request."""
    lease, permit, node, wire = leased_vector(db, tmp_path / "inputs")
    restarted = restart_database(db)

    def reserve(index: int) -> bool:
        try:
            reserve_vector(db if index % 2 == 0 else restarted, permit, node.node_id, wire.frozen)
        except VectorError:
            return False
        return True

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(4)))
        assert sum(results) == 1
        assert len(list_vector_attempts(restarted, lease.task_id)) == 1
        with restarted.session() as session:
            account = session.get(VectorAccountRow, permit.plan_id)
            assert account is not None
            assert account.requests == 1
            assert account.cost_nanos == wire.frozen.token_bound
    finally:
        restarted.engine.dispose()


@pytest.mark.parametrize("sent", [False, True])
def test_restart_reaper_never_resends_and_refunds_only_proven_unsent(
    db: Database, tmp_path: Path, *, sent: bool
) -> None:
    """A crash after fake dispatch keeps occupancy; a merely reserved request is safely refunded."""
    lease, permit, node, wire = leased_vector(db, tmp_path / "inputs")
    attempt = reserve_vector(db, permit, node.node_id, wire.frozen)
    if sent:
        FakeVectorTransport().send(db, permit, node, wire, attempt.id)
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = utcnow().timestamp() - 100
        shard.lease_expires_at = shard.heartbeat_at
        session.commit()
    restarted = restart_database(db)
    try:
        queue = DatabaseQueue(restarted)
        with ThreadPoolExecutor(max_workers=2) as pool:
            reaped = list(
                pool.map(lambda database: DatabaseQueue(database).reap(), (db, restarted))
            )
        assert sum(reaped) == 1
        assert queue.reap() == 0
        assert queue.claim() is None
        saved = list_vector_attempts(restarted, lease.task_id)
        assert len(saved) == 1
        assert saved[0].state == ("UNKNOWN" if sent else "REFUNDED")
        with restarted.session() as session:
            account = session.get(VectorAccountRow, permit.plan_id)
            assert account is not None
            assert account.requests == int(sent)
            assert account.cost_nanos == (wire.frozen.token_bound if sent else 0)
        task = query_task(restarted, lease.task_id)
        assert task.state == "FAILED"
        assert task.vector is not None
        assert task.vector.status == "failed"
        assert task.vector.nodes == ()
    finally:
        restarted.engine.dispose()


@pytest.mark.parametrize(
    "defect",
    [
        "missing_usage",
        "excess_usage",
        "boolean_usage",
        "negative_usage",
        "wrong_model",
        "wrong_index",
        "wrong_count",
        "wrong_dimension",
        "nan",
        "zero",
        "overflow",
        "redirect",
    ],
)
def test_bad_response_preserves_worst_occupancy_and_publishes_nothing(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    """Protocol or usage uncertainty must never become a zero-cost empty success."""
    original = FakeVectorTransport._respond  # noqa: SLF001  # Synthetic response fault injection.

    def respond(self: FakeVectorTransport, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        reply = original(self, node, wire)
        value = json.loads(reply.body)
        if defect == "missing_usage":
            del value["usage"]
        elif defect == "excess_usage":
            value["usage"]["total_tokens"] = wire.frozen.token_bound + 1
        elif defect in {"boolean_usage", "negative_usage"}:
            value["usage"]["total_tokens"] = True if defect == "boolean_usage" else -1
        elif defect == "wrong_model":
            value["model"] = "multimodal-embedding-v1"
        elif defect == "wrong_index":
            value["data"][0]["index"] = 1
        elif defect == "wrong_count":
            value["data"] = []
        elif defect == "wrong_dimension":
            value["data"][0]["embedding"] = [1.0]
        elif defect in {"nan", "zero", "overflow"}:
            value["data"][0]["embedding"] = [
                float("nan") if defect == "nan" else 0.0 if defect == "zero" else 1e100
            ] * 64
        return FakeReply(
            status=302 if defect == "redirect" else 200, body=json.dumps(value).encode()
        )

    monkeypatch.setattr(FakeVectorTransport, "_respond", respond)
    task = vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    assert task.state == "FAILED", task.error
    attempts = list_vector_attempts(db, task.id)
    assert len(attempts) == 1
    assert attempts[0].state == "UNKNOWN"
    assert attempts[0].reserved_nanos > 0
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0


def test_transport_rechecks_body_url_and_attempt_before_dispatch(
    db: Database, tmp_path: Path
) -> None:
    """A forged final body or destination cannot transition the reservation to sending."""
    lease, permit, node, wire = leased_vector(db, tmp_path / "inputs")
    attempt = reserve_vector(db, permit, node.node_id, wire.frozen)
    transport = FakeVectorTransport()
    with pytest.raises(VectorError, match="final_payload_changed"):
        transport.send(db, permit, node, wire.model_copy(update={"body": b"changed"}), attempt.id)
    changed = node.model_copy(
        update={
            "params": node.params.model_copy(
                update={"endpoint": "https://other.example.invalid/embeddings"}
            )
        }
    )
    with pytest.raises(VectorError, match="plan_mismatch"):
        transport.send(db, permit, changed, wire, attempt.id)
    assert list_vector_attempts(db, lease.task_id)[0].state == "RESERVED"


def test_second_dispatch_cannot_reuse_the_same_attempt(db: Database, tmp_path: Path) -> None:
    """A response lost after dispatch never authorizes a second send with the same attempt."""
    _, permit, node, wire = leased_vector(db, tmp_path / "inputs")
    attempt = reserve_vector(db, permit, node.node_id, wire.frozen)
    transport = FakeVectorTransport()
    transport.send(db, permit, node, wire, attempt.id)
    with pytest.raises(VectorError, match="dispatch_identity_invalid"):
        transport.send(db, permit, node, wire, attempt.id)


@pytest.mark.parametrize("raises", [False, True])
def test_untrusted_response_and_transport_errors_never_enter_logs(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    raises: bool,
) -> None:
    """Typed failures hide arbitrary fake response bodies and exception messages."""
    marker = "untrusted-response-marker"

    def respond(self: FakeVectorTransport, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        if raises:
            raise RuntimeError(marker)
        return FakeReply(body=json.dumps({"unexpected": marker}).encode())

    monkeypatch.setattr(FakeVectorTransport, "_respond", respond)
    task = vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    assert task.state == "FAILED"
    assert marker not in caplog.text
    assert marker not in (task.error or "")
    assert list_vector_attempts(db, task.id)[0].state == "UNKNOWN"
