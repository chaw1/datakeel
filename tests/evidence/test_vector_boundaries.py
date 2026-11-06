# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Observable refusal anchors for tool entry, repeated dispatch and failed publication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.datasets import materialize_files
from datakeel.evidence.vector_execution import VectorExecution
from datakeel.evidence.vector_transport import FakeVectorTransport
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.pipeline import run_pipeline
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_budget import reserve_vector
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.vector_helpers import leased_vector, vector_dataset, vector_prepare

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_tool_approval_guard_is_observable(db: Database, tmp_path: Path) -> None:
    """A tool request cannot create the approval that a person must supply."""
    plan = vector_prepare(db, vector_dataset(db, tmp_path / "inputs"))
    refused = False
    try:
        approve_plan(
            db,
            plan.id,
            ApprovalDecision(approve=True, plan_digest=plan.plan_digest),
            access=AccessContext(actor="local", entry="mcp", scope="query"),
        )
    except VectorError:
        refused = True
    assert refused


def test_redispatch_guard_is_observable(db: Database, tmp_path: Path) -> None:
    """The durable SENDING state cannot be dispatched a second time."""
    _, permit, node, wire = leased_vector(db, tmp_path / "inputs")
    attempt = reserve_vector(db, permit, node.node_id, wire.frozen)
    transport = FakeVectorTransport()
    transport.send(db, permit, node, wire, attempt.id)
    refused = False
    try:
        transport.send(db, permit, node, wire, attempt.id)
    except VectorError:
        refused = True
    assert refused


def test_error_finish_discards_all_pending_vectors(db: Database, tmp_path: Path) -> None:
    """Even a caller that supplies successful pending products cannot publish them on failure."""
    lease, permit, _, _ = leased_vector(db, tmp_path / "inputs")
    context = EvidenceExecutionContext(
        task_id=lease.task_id,
        shard_id=lease.shard_id,
        version_id=lease.input_version_id or "missing",
    )
    executor = VectorExecution(db, context, permit)
    outputs = run_pipeline(
        materialize_files(lease.inputs),
        tmp_path / "outputs",
        lease.pipeline,
        operator_executor=executor.execute_node,
    )
    assert executor.pending
    assert DatabaseQueue(db).finish(
        lease,
        outputs,
        [],
        error="vector_fixture_terminal_failure",
        evidence=tuple(executor.pending),
    )
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0
