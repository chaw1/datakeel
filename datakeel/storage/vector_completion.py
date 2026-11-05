# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforce the whole vector DAG as one fenced publication unit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import PipelineParams
from datakeel.core.datasheet_execution import DatasheetCompletion
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.evidence_execution import PendingExtraction
from datakeel.core.kg_execution import KGCompletion
from datakeel.core.vector_models import VECTOR_OPERATORS, VectorError, VectorPermit
from datakeel.evidence.vector_plan import has_vectors
from datakeel.pipeline.models import Pipeline
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.vector_authorization import authorize_vector
from datakeel.storage.vector_planning import verify_vector_params
from datakeel.storage.vector_rows import VectorAttemptRow
from datakeel.worker_store.rows import TaskRow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.storage.task_queue import Lease

type Completion = tuple[PendingExtraction, ...] | KGCompletion | DqCompletion | DatasheetCompletion


def has_vector_work(session: Session, task_id: str, task: TaskRow | None) -> bool:
    """Retain nonretryable billing identity even if a queued DAG was removed or modified."""
    attempted = (
        session.scalar(
            select(VectorAttemptRow.id).where(VectorAttemptRow.task_id == task_id).limit(1)
        )
        is not None
    )
    return attempted or (
        task is not None
        and has_vectors(Pipeline.model_validate(task.pipeline) if task.pipeline else None)
    )


def validate_vector_completion(
    session: Session, lease: Lease, evidence: Completion, error: str | None
) -> Completion:
    """Reject partial success and drop all new pending facts on any terminal vector failure."""
    task = session.get(TaskRow, lease.task_id)
    pipeline = Pipeline.model_validate(task.pipeline) if task and task.pipeline else None
    if not has_vectors(pipeline):
        return evidence
    if error:
        return ()
    run = session.scalar(select(ActionRunRow).where(ActionRunRow.task_id == lease.task_id))
    plan = session.get(ActionPlanRow, run.plan_id) if run else None
    if run is None or plan is None:
        msg = "vector_requires_consumed_human_approval"
        raise VectorError(msg)
    permit = VectorPermit(
        plan_id=run.plan_id,
        plan_digest=str(plan.payload["plan_digest"]),
        run_id=run.id,
        task_id=lease.task_id,
        shard_id=lease.shard_id,
        owner=lease.owner,
        version_id=str(plan.payload["canonical_params"].get("version_id") or ""),
    )
    authorize_vector(session, permit)
    approved = ActionPlan.model_validate({**plan.payload, "status": plan.status})
    verify_vector_params(
        session, approved, PipelineParams.model_validate(approved.canonical_params)
    )
    expected: set[str] = (
        {node.id for node in pipeline.nodes if node.operator in VECTOR_OPERATORS}
        if pipeline
        else set()
    )
    if not isinstance(evidence, tuple):
        msg = "vector_publication_incomplete"
        raise VectorError(msg)
    actual = [
        item.event.params.get("node_id")
        for item in evidence
        if item.event.operator in VECTOR_OPERATORS
    ]
    if set(actual) != expected or len(actual) != len(expected):
        msg = "vector_publication_incomplete"
        raise VectorError(msg)
    if any(product.mode != "fake" for item in evidence for product in item.bundle.vector_products):
        msg = "vector_publication_mode_mismatch"
        raise VectorError(msg)
    return evidence
