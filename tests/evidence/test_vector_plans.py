# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""W-E-A2: complete branch freezing and refusal of every unsigned execution route."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.parameters import PipelineParams
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.models import JsonDocument
from datakeel.core.vector_models import EmbedParams, VectorError
from datakeel.dataset_store.datasets import materialize_files
from datakeel.evidence.vector_execution import VectorExecution
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.pipeline import Node, Pipeline, run_pipeline
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.vector_budget import list_vector_attempts
from datakeel.worker.runner import execute
from datakeel.worker_store.rows import TaskRow
from tests.evidence.vector_helpers import (
    leased_vector,
    vector_dataset,
    vector_pipeline,
    vector_prepare,
    vector_schedule,
)


def test_worker_refuses_omitted_branch_inputs_before_dispatch(db: Database, tmp_path: Path) -> None:
    """Membership must equal the frozen actual branch, rather than being an approved subset."""
    lease, permit, _, _ = leased_vector(db, tmp_path / "inputs")
    context = EvidenceExecutionContext(
        task_id=lease.task_id,
        shard_id=lease.shard_id,
        version_id=lease.input_version_id or "missing",
    )
    execution = VectorExecution(db, context, permit)
    assert lease.pipeline is not None
    with pytest.raises(VectorError, match="branch_inputs_changed"):
        execution.execute_node(
            lease.pipeline.nodes[0], materialize_files(lease.inputs[:1]), tmp_path
        )
    assert list_vector_attempts(db, lease.task_id) == ()


def test_changed_runtime_threshold_is_outside_the_signed_dag(db: Database, tmp_path: Path) -> None:
    """Even a valid duplicate node id cannot execute altered parameters under the same permit."""
    lease, permit, _, _ = leased_vector(db, tmp_path / "inputs")
    context = EvidenceExecutionContext(
        task_id=lease.task_id,
        shard_id=lease.shard_id,
        version_id=lease.input_version_id or "missing",
    )
    execution = VectorExecution(db, context, permit)
    assert lease.pipeline is not None
    changed = lease.pipeline.nodes[1].model_copy(update={"params": {"threshold": 0.5}})
    with pytest.raises(VectorError, match="hidden_or_changed_node"):
        execution.execute_node(changed, materialize_files(lease.inputs), tmp_path)


if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_prepare_freezes_inactive_branch_final_payload_and_full_url(
    db: Database, tmp_path: Path
) -> None:
    """Even an inactive external branch requires approval and a complete worst envelope."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    original = vector_pipeline()
    condition = Node(
        id="branch", kind="condition", inputs={"files": "$input.files"}, params={"min_count": 99}
    )
    embed = original.nodes[0].model_copy(update={"inputs": {"files": "branch.true"}})
    pipeline = original.model_copy(update={"nodes": [condition, embed, original.nodes[1]]})
    plan = vector_prepare(db, dataset, pipeline)
    prepared = PipelineParams.model_validate(plan.canonical_params).vector_prepared
    assert plan.external
    assert plan.requires_approval
    assert prepared is not None
    assert prepared.worst_requests == 3
    assert len(prepared.nodes[0].inputs) == 3
    assert all(item.body_hash and item.payload_hash for item in prepared.nodes[0].inputs)
    assert prepared.nodes[0].params.endpoint == "https://embedding.example.invalid/v1/embeddings"
    assert prepared.nodes[0].params.policy.real_budget_cny == 0
    task_id = vector_schedule(db, plan)
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    assert list_vector_attempts(db, task_id) == ()


@pytest.mark.parametrize("shards", [1, 2])
def test_direct_submit_and_sharding_are_rejected(db: Database, tmp_path: Path, shards: int) -> None:
    """Neither a direct task nor split pairwise evaluation can bypass preparation."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    with pytest.raises((VectorError, ValidationError)):
        DatabaseQueue(db).submit(dataset, "direct", vector_pipeline(), shards=shards)


def test_direct_pipeline_operator_is_nonexecutable(db: Database, tmp_path: Path) -> None:
    """The registered operators refuse calls without the signed worker executor."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    files = materialize_files(source_manifest(db, dataset)[1])
    with pytest.raises(VectorError, match="consumed_human_approval"):
        run_pipeline(files, tmp_path / "outputs", vector_pipeline())


def test_unsigned_action_has_no_task_or_fake_attempt(db: Database, tmp_path: Path) -> None:
    """Zero fake price is still external and cannot suppress human consent."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    pipeline = vector_pipeline()
    embed = pipeline.nodes[0].model_copy(update={"params": {"policy": {"nanos_per_token": 0}}})
    plan = vector_prepare(
        db, dataset, pipeline.model_copy(update={"nodes": [embed, pipeline.nodes[1]]})
    )
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert plan.requires_approval


@pytest.mark.parametrize("entry", ["mcp", "agent"])
def test_tool_cannot_approve_or_execute_even_a_human_signed_plan(
    db: Database, tmp_path: Path, entry: str
) -> None:
    """Actual tool entry context is checked on both approval and execution boundaries."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    plan = vector_prepare(db, dataset)
    access = AccessContext.model_validate({"actor": "local", "entry": entry, "scope": "query"})
    decision = ApprovalDecision(approve=True, plan_digest=plan.plan_digest)
    with pytest.raises(VectorError, match="human_execution"):
        approve_plan(db, plan.id, decision, access=access)
    approve_plan(db, plan.id, decision)
    with pytest.raises(VectorError, match="human_execution"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest), access=access)


def test_agent_attributed_plan_cannot_be_signed(db: Database, tmp_path: Path) -> None:
    """An agent id cannot be dropped by switching the execution entry point."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    plan = prepare_action(
        db,
        "run_pipeline",
        JsonDocument.model_validate(
            {"dataset_id": dataset, "pipeline": vector_pipeline().model_dump(mode="json")}
        ),
        ActionContext(agent_id="fixture-agent"),
    )
    with pytest.raises(VectorError, match="human_execution"):
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))


def test_transformed_inactive_upstream_is_unfreezable(db: Database, tmp_path: Path) -> None:
    """A condition cannot hide a byte-changing ancestor from prepare."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    original = vector_pipeline()
    route = Node(id="route", kind="route", inputs={"files": "$input.files"})
    transform = Node(id="transform", operator="text.pii_redact", inputs={"files": "route.text"})
    condition = Node(
        id="branch", kind="condition", inputs={"files": "transform.files"}, params={"min_count": 99}
    )
    embed = original.nodes[0].model_copy(update={"inputs": {"files": "branch.true"}})
    pipeline = original.model_copy(
        update={"nodes": [route, transform, condition, embed, original.nodes[1]]}
    )
    with pytest.raises(VectorError, match="unfreezable"):
        vector_prepare(db, dataset, pipeline)


def test_changed_original_refuses_approval(db: Database, tmp_path: Path) -> None:
    """A frozen final-payload hash is rechecked against actual local bytes."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    plan = vector_prepare(db, dataset)
    file = materialize_files(source_manifest(db, dataset)[1])[0]

    Path(file.path).write_bytes(b"modified fixture")
    with pytest.raises(VectorError, match="content_or_modality_changed"):
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))


def test_hidden_queued_node_is_rejected_before_transport(db: Database, tmp_path: Path) -> None:
    """A queued DAG mutation cannot reuse the original consumed signature."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    task_id = vector_schedule(db, vector_prepare(db, dataset))
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.pipeline is not None
        task.pipeline = {**task.pipeline, "outputs": ["embed.files"]}
        session.commit()
    assert execute(queue, lease)
    assert list_vector_attempts(db, task_id) == ()


def test_removed_external_subgraph_is_rejected_by_direct_worker(
    db: Database, tmp_path: Path
) -> None:
    """Removing every vector marker cannot bypass the signed external DAG."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    task_id = vector_schedule(db, vector_prepare(db, dataset))
    local = Pipeline(
        nodes=[Node(id="local", operator="file.dedup", inputs={"files": "$input.files"})],
        outputs=["local.files"],
    )
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        task.pipeline = local.model_dump(mode="json")
        session.commit()
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.state == "FAILED"
        assert "vector_queued_dag_changed" in (task.error or "")
    assert list_vector_attempts(db, task_id) == ()


@pytest.mark.parametrize(
    "params",
    [
        {"mode": "real"},
        {"mode": "recording"},
        {"tokenizer": "unknown"},
        {"endpoint": "https://embedding.example.invalid/v1/embeddings?option=fixture"},
        {"endpoint": "http://embedding.example.invalid/embeddings"},
    ],
)
def test_fake_configuration_cannot_enable_real_or_unknown_bounds(params: object) -> None:
    """No runtime mode or destination configuration can create a real vector adapter."""
    with pytest.raises(ModelValidationError):
        EmbedParams.model_validate(params)


def test_worker_rejects_changed_source_version_before_dispatch(
    db: Database, tmp_path: Path
) -> None:
    """An owned lease cannot substitute source provenance under the same approval."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    task_id = vector_schedule(db, vector_prepare(db, dataset))
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    changed = lease.model_copy(update={"input_version_id": "unapproved-version"})
    assert execute(queue, changed)
    assert list_vector_attempts(db, task_id) == ()
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.state == "FAILED"
        assert "vector_execution_identity_changed" in (task.error or "")
