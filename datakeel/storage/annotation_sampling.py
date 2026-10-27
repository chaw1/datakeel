# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist reproducible sample plans and freeze complete inspection evidence for actions."""

import hashlib
import math

from sqlalchemy.orm import Session

from datakeel.core.annotation_aql import lookup_aql
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.annotation_sampling import (
    AnnotationAcceptanceParams,
    SamplingPlan,
    SamplingRequest,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import utcnow
from datakeel.storage.annotation_rows import AnnotationSamplingRow
from datakeel.storage.annotation_store import require_batch
from datakeel.storage.database import Database
from datakeel.storage.object_projection import content_digest


def select_sample(sample_ids: tuple[str, ...], count: int, seed: int) -> tuple[str, ...]:
    """Sample without replacement by SHA-256 ranking of seed and sorted unit identities."""
    ranked = sorted(
        set(sample_ids),
        key=lambda identifier: (
            hashlib.sha256(f"{seed}\0{identifier}".encode()).digest(),
            identifier,
        ),
    )
    return tuple(sorted(ranked[:count]))


def _sampling_plan(
    batch: AnnotationBatch, request: SamplingRequest, template: SamplingPlan
) -> SamplingPlan:
    identifiers = tuple(sorted({item.sample_id for item in batch.annotations}))
    lookup = lookup_aql(len(identifiers), request.aql) if request.method == "aql" else None
    count = (
        lookup.sample_size if lookup else max(1, math.ceil(len(identifiers) * (request.ratio or 1)))
    )
    acceptance = lookup.acceptance_number if lookup else (request.acceptance_number or 0)
    if acceptance >= count:
        message = "Acceptance number must be smaller than the inspected sample size"
        raise ValidationError(message)
    return template.model_copy(
        update={
            "lot_size": len(identifiers),
            "sample_size": count,
            "sample_ids": select_sample(identifiers, count, request.seed),
            "acceptance_number": acceptance,
            "rejection_number": acceptance + 1,
            "code_letter": lookup.code_letter if lookup else None,
            "effective_code_letter": lookup.effective_code_letter if lookup else None,
        }
    )


def create_sampling_plan(db: Database, dataset_id: str, request: SamplingRequest) -> SamplingPlan:
    """Persist an idempotent sample selection; the request hash is its explicit retry key."""
    identifier = "asp_" + content_digest(
        {"dataset_id": dataset_id, **request.model_dump(mode="json")}
    )
    with db.session() as session:
        db.lock_writes(session)
        batch_row = require_batch(session, dataset_id, request.batch_id)
        previous = session.get(AnnotationSamplingRow, identifier)
        if previous is not None:
            return SamplingPlan.model_validate(previous.payload)
        template = SamplingPlan(
            id=identifier,
            batch_id=batch_row.id,
            dataset_id=dataset_id,
            version_id=batch_row.version_id,
            batch_digest=content_digest(batch_row.batch),
            method=request.method,
            aql=request.aql if request.method == "aql" else None,
            ratio=request.ratio,
            seed=request.seed,
            lot_size=0,
            sample_size=0,
            sample_ids=(),
            acceptance_number=0,
            rejection_number=1,
            created_at=utcnow(),
        )
        plan = _sampling_plan(AnnotationBatch.model_validate(batch_row.batch), request, template)
        session.add(
            AnnotationSamplingRow(
                id=plan.id,
                batch_id=batch_row.id,
                payload=plan.model_dump(mode="json"),
                created_at=plan.created_at.timestamp(),
            )
        )
        session.commit()
    return plan


def require_inspection_plan(session: Session, params: AnnotationAcceptanceParams) -> SamplingPlan:
    """Reject wrong scopes, changed batches and partial or out-of-sample review submissions."""
    batch = require_batch(session, params.dataset_id, params.batch_id)
    row = session.get(AnnotationSamplingRow, params.sampling_id)
    if row is None or row.batch_id != batch.id:
        message = "Annotation sampling plan was not found for this batch"
        raise NotFoundError(message)
    plan = SamplingPlan.model_validate(row.payload)
    if (
        plan.dataset_id != params.dataset_id
        or plan.version_id != params.version_id
        or batch.version_id != params.version_id
        or plan.batch_digest != content_digest(batch.batch)
    ):
        message = "Inspection scope or frozen annotation digest does not match"
        raise ConflictError(message)
    if {check.sample_id for check in params.checks} != set(plan.sample_ids):
        message = "Inspection must review every frozen sampled unit exactly once"
        raise ValidationError(message)
    request = SamplingRequest(
        batch_id=batch.id,
        method=plan.method,
        aql=plan.aql or 2.5,
        ratio=plan.ratio,
        acceptance_number=plan.acceptance_number if plan.method == "ratio" else None,
        seed=plan.seed,
    )
    expected = _sampling_plan(AnnotationBatch.model_validate(batch.batch), request, plan)
    if expected != plan:
        message = "Stored sampling selection does not match its reproducible plan"
        raise ConflictError(message)
    return plan


def annotation_snapshot(session: Session, params: AnnotationAcceptanceParams) -> str:
    """Bind raw annotations, saved metrics and the entire reproducible sampling plan."""
    sampling = require_inspection_plan(session, params)
    batch = require_batch(session, params.dataset_id, params.batch_id)
    return content_digest(
        {"batch": batch.batch, "report": batch.report, "sampling": sampling.model_dump(mode="json")}
    )
