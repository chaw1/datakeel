# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append version-owned annotation batches and read immutable quality audit history."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.annotation_qa import changed_samples, compare_rework, evaluate_annotations
from datakeel.core.annotation_models import AnnotationBatch, ReworkComparison
from datakeel.core.annotation_sampling import (
    AnnotationImportRequest,
    AnnotationQualityOverview,
    AnnotationQualityReport,
    SamplingInspection,
    SamplingPlan,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.annotation_rows import (
    AnnotationBatchRow,
    AnnotationInspectionRow,
    AnnotationSamplingRow,
)
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.object_projection import content_digest

MAX_BATCH_SAMPLES = 10000
MAX_BATCH_ANNOTATIONS = 100000


def require_annotation_version(session: Session, dataset_id: str, version_id: str) -> VersionRow:
    """Reject cross-dataset versions before accepting annotation or sampling identities."""
    require_dataset(session, dataset_id)
    version = session.get(VersionRow, version_id)
    if version is None or version.dataset_id != dataset_id:
        message = "Annotation dataset version was not found"
        raise NotFoundError(message)
    return version


def require_batch(session: Session, dataset_id: str, batch_id: str) -> AnnotationBatchRow:
    """Read one batch only within its dataset scope and verify its input fingerprint."""
    row = session.get(AnnotationBatchRow, batch_id)
    if row is None or row.dataset_id != dataset_id:
        message = "Annotation batch was not found"
        raise NotFoundError(message)
    report = AnnotationQualityReport.model_validate(row.report)
    if content_digest(row.batch) != report.batch_digest:
        message = "Stored annotation batch does not match its frozen digest"
        raise ConflictError(message)
    return row


def _validate_membership(version: VersionRow, batch: AnnotationBatch) -> None:
    samples = {item.sample_id for item in batch.annotations}
    files = {str(item["id"]) for item in version.manifest}
    if (
        not samples
        or len(samples) > MAX_BATCH_SAMPLES
        or len(batch.annotations) > MAX_BATCH_ANNOTATIONS
    ):
        message = "Annotation batches require 1 to 10000 samples and at most 100000 annotations"
        raise ValidationError(message)
    if not samples <= files:
        message = "Annotation samples must belong to the selected immutable version"
        raise ValidationError(message)
    if any(
        pair.sample_id not in samples or pair.other_sample_id not in samples
        for pair in batch.near_duplicates
    ):
        message = "Near-duplicate endpoints must belong to this annotation batch"
        raise ValidationError(message)


def _compare(
    session: Session, dataset_id: str, request: AnnotationImportRequest
) -> ReworkComparison | None:
    if request.rework_of is None:
        return None
    previous = require_batch(session, dataset_id, request.rework_of)
    if previous.version_id != request.version_id:
        message = "Rework comparison requires the same dataset version"
        raise ValidationError(message)
    before = AnnotationBatch.model_validate(previous.batch)
    comparison = compare_rework(before, request.batch)
    defects = {
        check.sample_id
        for row in session.scalars(
            select(AnnotationInspectionRow).where(AnnotationInspectionRow.batch_id == previous.id)
        )
        for check in SamplingInspection.model_validate(row.payload).checks
        if check.defective
    }
    return comparison.model_copy(
        update={
            "inspection_defects": len(defects),
            "inspection_defects_changed": len(defects & changed_samples(before, request.batch)),
        }
    )


def _new_report(
    session: Session, dataset_id: str, request: AnnotationImportRequest
) -> AnnotationQualityReport:
    comparison = _compare(session, dataset_id, request)
    return AnnotationQualityReport(
        id=new_id(),
        dataset_id=dataset_id,
        version_id=request.version_id,
        name=request.name,
        batch_digest=content_digest(request.batch.model_dump(mode="json")),
        sample_count=len({item.sample_id for item in request.batch.annotations}),
        annotation_count=len(request.batch.annotations),
        result=evaluate_annotations(request.batch),
        comparison=comparison,
        rework_of=request.rework_of,
        created_at=utcnow(),
    )


def import_annotations(
    db: Database, dataset_id: str, request: AnnotationImportRequest
) -> AnnotationQualityReport:
    """Save generated metrics and rework history atomically; identical retries reuse a report."""
    with db.session() as session:
        db.lock_writes(session)
        report = import_annotations_in_session(session, dataset_id, request)
        session.commit()
    return report


def import_annotations_in_session(
    session: Session, dataset_id: str, request: AnnotationImportRequest
) -> AnnotationQualityReport:
    """Reuse the annotation importer inside a caller-owned atomic production transaction."""
    request_digest = content_digest(request.model_dump(mode="json"))
    version = require_annotation_version(session, dataset_id, request.version_id)
    _validate_membership(version, request.batch)
    previous = session.scalar(
        select(AnnotationBatchRow).where(
            AnnotationBatchRow.dataset_id == dataset_id,
            AnnotationBatchRow.idempotency_key == request.idempotency_key,
        )
    )
    if previous is not None:
        if previous.request_digest != request_digest:
            message = "Annotation import identity already belongs to different inputs"
            raise ConflictError(message)
        return AnnotationQualityReport.model_validate(previous.report)
    report = _new_report(session, dataset_id, request)
    session.add(
        AnnotationBatchRow(
            id=report.id,
            dataset_id=dataset_id,
            version_id=request.version_id,
            idempotency_key=request.idempotency_key,
            request_digest=request_digest,
            batch=request.batch.model_dump(mode="json"),
            report=report.model_dump(mode="json"),
            created_at=report.created_at.timestamp(),
        )
    )
    return report


def get_annotation_quality(
    db: Database, dataset_id: str, version_id: str | None = None
) -> AnnotationQualityOverview:
    """Read exact-version or complete-dataset annotation history with no recalculation."""
    with db.session() as session:
        return read_annotation_quality(session, dataset_id, version_id)


def read_annotation_quality(
    session: Session, dataset_id: str, version_id: str | None = None
) -> AnnotationQualityOverview:
    """Project reports inside a caller-owned read transaction without nesting sessions."""
    require_dataset(session, dataset_id)
    if version_id is not None:
        require_annotation_version(session, dataset_id, version_id)
    query = select(AnnotationBatchRow).where(AnnotationBatchRow.dataset_id == dataset_id)
    if version_id is not None:
        query = query.where(AnnotationBatchRow.version_id == version_id)
    rows = list(session.scalars(query.order_by(AnnotationBatchRow.created_at.desc())))
    batches = tuple(AnnotationQualityReport.model_validate(row.report) for row in rows)
    identifiers = [row.id for row in rows]
    inspections = session.scalars(
        select(AnnotationInspectionRow)
        .where(AnnotationInspectionRow.batch_id.in_(identifiers))
        .order_by(AnnotationInspectionRow.created_at.desc())
    )
    plans = session.scalars(
        select(AnnotationSamplingRow)
        .where(AnnotationSamplingRow.batch_id.in_(identifiers))
        .order_by(AnnotationSamplingRow.created_at.desc())
    )
    return AnnotationQualityOverview(
        dataset_id=dataset_id,
        version_id=version_id,
        latest=batches[0] if batches else None,
        batches=batches,
        inspections=tuple(SamplingInspection.model_validate(row.payload) for row in inspections),
        sampling_plans=tuple(SamplingPlan.model_validate(row.payload) for row in plans),
    )
