# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforce the whole vector DAG as one fenced publication unit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.parameters import PipelineParams
from datakeel.core.vector_models import VECTOR_OPERATORS, VectorError, VectorPermit
from datakeel.storage.vector_authorization import authorize_vector, vector_completion_plan
from datakeel.storage.vector_planning import verify_vector_params
from datakeel.storage.vector_reports import has_vector_work

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.core.evidence_execution import PendingExtraction
    from datakeel.worker_store.completion import CompletionRequest


def validate_vector_completion(
    session: Session,
    request: CompletionRequest,
    evidence: tuple[PendingExtraction, ...],
    error: str | None,
) -> tuple[PendingExtraction, ...]:
    """Reject partial success and drop all new pending facts on any terminal vector failure."""
    pipeline = request.pipeline
    if not has_vector_work(session, request.task_id, pipeline):
        return evidence
    if error:
        return ()
    run_id, approved = vector_completion_plan(session, request.task_id)
    permit = VectorPermit(
        plan_id=approved.id,
        plan_digest=approved.plan_digest,
        run_id=run_id,
        task_id=request.task_id,
        shard_id=request.shard_id,
        owner=request.owner,
        version_id=str(approved.canonical_params.get("version_id") or ""),
    )
    authorize_vector(session, permit)
    verify_vector_params(
        session, approved, PipelineParams.model_validate(approved.canonical_params)
    )
    expected: set[str] = (
        {node.id for node in pipeline.nodes if node.operator in VECTOR_OPERATORS}
        if pipeline
        else set()
    )
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
