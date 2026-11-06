# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze and revalidate vector requests using the selected immutable local version."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import PipelineParams
from datakeel.core.models import BoundaryModel, FileItem
from datakeel.core.vector_models import VectorError, require_local_vector_objects
from datakeel.dataset_store.datasets import materialize_files
from datakeel.dataset_store.rows import DatasetRow, VersionRow
from datakeel.evidence.vector_plan import freeze_vectors, has_vectors


def _files(session: Session, params: PipelineParams) -> list[FileItem]:
    require_local_vector_objects()
    version = session.get(VersionRow, params.version_id)
    if version is None or version.dataset_id != params.dataset_id:
        msg = "vector_source_version_missing"
        raise VectorError(msg)
    return materialize_files(version.manifest)


def prepare_vector_params(session: Session, parsed: BoundaryModel) -> BoundaryModel:
    """Resolve a missing version once; never permit client-provided prepared payloads."""
    if not isinstance(parsed, PipelineParams) or not has_vectors(parsed.pipeline):
        if isinstance(parsed, PipelineParams) and parsed.vector_prepared is not None:
            msg = "unexpected_vector_prepared"
            raise VectorError(msg)
        return parsed
    version_id = parsed.version_id or session.scalar(
        select(VersionRow.id)
        .where(VersionRow.dataset_id == parsed.dataset_id)
        .order_by(VersionRow.created_at.desc(), VersionRow.id.desc())
        .limit(1)
    )
    if version_id is None or session.get(DatasetRow, parsed.dataset_id) is None:
        msg = "vector_source_version_missing"
        raise VectorError(msg)
    resolved = parsed.model_copy(update={"version_id": version_id})
    if resolved.pipeline is None:
        msg = "vector_pipeline_missing"
        raise VectorError(msg)
    prepared = freeze_vectors(resolved.pipeline, _files(session, resolved))
    if not prepared.nodes:
        msg = "vector_embedding_node_missing"
        raise VectorError(msg)
    policies = [node.params.policy for node in prepared.nodes]
    if any(policy != policies[0] for policy in policies):
        msg = "vector_requires_one_budget_policy"
        raise VectorError(msg)
    if (
        prepared.worst_requests > policies[0].max_requests
        or prepared.worst_cost_nanos > policies[0].max_cost_nanos
    ):
        msg = "vector_budget_exceeded"
        raise VectorError(msg)
    return resolved.model_copy(update={"vector_prepared": prepared})


def verify_vector_params(session: Session, plan: ActionPlan, params: BoundaryModel) -> None:
    """Compare recomputed bytes and the whole branch closure before approval or execution."""
    if isinstance(params, PipelineParams) and has_vectors(params.pipeline):
        if params.pipeline is None or params.vector_prepared is None or not plan.external:
            msg = "vector_prepared_plan_required"
            raise VectorError(msg)
        if freeze_vectors(params.pipeline, _files(session, params)) != params.vector_prepared:
            msg = "vector_frozen_plan_changed"
            raise VectorError(msg)
