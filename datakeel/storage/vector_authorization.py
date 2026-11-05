# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify durable consumed human approval, exact DAG and current worker fencing."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import PipelineParams
from datakeel.actions.policy import plan_digest
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import utcnow
from datakeel.core.vector_models import VectorError, VectorPermit, VectorPrepared, vector_hash
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow, ApprovalRow
from datakeel.storage.database import Database
from datakeel.worker_store.rows import ShardRow, TaskRow


def require_vector_human(plan: ActionPlan, access: AccessContext | None) -> None:
    """Deny tool-origin approval and execution even after a person signed the plan."""
    if (
        plan.action_type == "run_pipeline"
        and plan.external
        and (plan.agent_id is not None or (access is not None and access.entry in {"mcp", "agent"}))
    ):
        msg = "vector_human_execution_required"
        raise VectorError(msg)


def vector_task_matches(task: TaskRow | None, params: PipelineParams) -> bool:
    """Bind dataset, immutable source version and complete DAG to the scheduled task."""
    return (
        task is not None
        and params.pipeline is not None
        and task.dataset_id == params.dataset_id
        and task.input_version_id == params.version_id
        and task.pipeline == params.pipeline.model_dump(mode="json")
    )


def authorize_vector(session: Session, permit: VectorPermit) -> VectorPrepared:
    """Recheck persisted identity, approval, pipeline and lease inside the caller lock."""
    run = session.get(ActionRunRow, permit.run_id)
    stored = session.get(ActionPlanRow, permit.plan_id)
    task = session.get(TaskRow, permit.task_id)
    shard = session.get(ShardRow, permit.shard_id)
    approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == permit.plan_id))
    if (
        run is None
        or stored is None
        or task is None
        or shard is None
        or approval is None
        or run.plan_id != permit.plan_id
        or run.task_id != permit.task_id
        or run.status not in {"QUEUED", "RUNNING"}
        or stored.status != "EXECUTED"
        or approval.status != "APPROVED"
        or not approval.consumed
        or task.state not in {"QUEUED", "RUNNING"}
        or task.total_shards != 1
        or shard.task_id != task.id
        or shard.state != "RUNNING"
        or shard.lease_owner != permit.owner
        or (shard.lease_expires_at or 0) <= utcnow().timestamp()
    ):
        msg = "vector_approval_or_lease_invalid"
        raise VectorError(msg)
    plan = ActionPlan.model_validate({**stored.payload, "status": stored.status})
    params = PipelineParams.model_validate(plan.canonical_params)
    if (
        not plan.external
        or plan.action_type != "run_pipeline"
        or plan.agent_id is not None
        or plan.plan_digest != permit.plan_digest
        or plan_digest(plan) != permit.plan_digest
        or approval.plan_digest != permit.plan_digest
        or approval.actor != plan.actor
        or not vector_task_matches(task, params)
        or permit.version_id != params.version_id
        or task.idempotency_key != f"action:{permit.plan_id}"
        or params.vector_prepared is None
    ):
        msg = "vector_plan_identity_invalid"
        raise VectorError(msg)
    if params.vector_prepared.dag_hash != vector_hash(task.pipeline):
        msg = "vector_dag_changed"
        raise VectorError(msg)
    return params.vector_prepared


def vector_permit(db: Database, task_id: str, shard_id: str, owner: str) -> VectorPermit:
    """Find only an authoritative action run; direct queue submissions have no permit."""
    with db.session() as session:
        run = session.scalar(select(ActionRunRow).where(ActionRunRow.task_id == task_id))
        if run is None:
            msg = "vector_requires_consumed_human_approval"
            raise VectorError(msg)
        plan = session.get(ActionPlanRow, run.plan_id)
        if plan is None:
            msg = "vector_plan_missing"
            raise VectorError(msg)
        permit = VectorPermit(
            plan_id=run.plan_id,
            plan_digest=str(plan.payload["plan_digest"]),
            run_id=run.id,
            task_id=task_id,
            shard_id=shard_id,
            owner=owner,
            version_id=str(plan.payload["canonical_params"].get("version_id") or ""),
        )
        authorize_vector(session, permit)
        return permit


def authorize_vector_node(session: Session, permit: VectorPermit, node: Node) -> VectorPrepared:
    """Reject altered thresholds, wiring or hidden callbacks outside the complete signed DAG."""
    prepared = authorize_vector(session, permit)
    task = session.get(TaskRow, permit.task_id)
    pipeline = Pipeline.model_validate(task.pipeline) if task else None
    if pipeline is None or node not in pipeline.nodes:
        msg = "vector_hidden_or_changed_node"
        raise VectorError(msg)
    return prepared
