# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""AI pre-review at submission: P26 suspicion rules, the project template and draft agreement.

The score and every reason are stored against the submitted revision. In group and team
projects a high-risk submission is always reviewed; a low-risk one is reviewed when its
reproducible draw falls under the project's review sample rate (100% by default, so every
submission is reviewed as before) and is otherwise approved with an audit note. Personal
projects only record the result for the annotator to see; nothing is blocked.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.annotation_qa import (
    HIGH_RISK,
    compare_records,
    disagreement_reason,
    find_suspicions,
    finding_reason,
    record_objects,
    risk_score,
    sample_draw,
)
from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord, NearDuplicatePair
from datakeel.core.errors import ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.prelabel_models import AIReview, ObjectRef, RiskReason
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.operators.evidence.contracts import read_near_duplicate
from datakeel.storage.production_ai_rows import ProductionAIReviewRow
from datakeel.storage.production_assignments import finish_assignment
from datakeel.storage.production_catalog import require_complete_attributes, validate_annotation
from datakeel.storage.production_prelabel_refs import object_confidences
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow
from datakeel.storage.production_task_images import sample_hash, sample_keys
from datakeel.storage.production_tasks import transition_task
from datakeel.storage.workbench_risk import prelabel_difference

CONTEXT_LIMIT = 500
EXEMPT_NOTE = "AI 预审低风险，按抽检比例免审 / AI pre-review low risk, exempt by review sampling"  # noqa: RUF001  # The audit wording is specified in Chinese.
_CONTEXT_STATES = ("submitted", "in_review", "approved", "finalized")


def _template_reasons(
    session: Session, project: Project, annotation: AnnotationRecord
) -> list[RiskReason]:
    try:
        validate_annotation(session, project, annotation, complete=True)
        require_complete_attributes(session, project, annotation)
    except ValidationError as error:
        return [RiskReason(code="template_violation", weight=0.9, message=str(error))]
    return []


def _context(
    session: Session, project: Project, task: ProductionTaskRow, head: AnnotationRecord
) -> list[AnnotationRecord]:
    rows = session.scalars(
        select(ProductionTaskRow)
        .where(
            ProductionTaskRow.project_id == project.id,
            ProductionTaskRow.id != task.id,
            ProductionTaskRow.state.in_(_CONTEXT_STATES),
        )
        .order_by(ProductionTaskRow.id.desc())
        .limit(CONTEXT_LIMIT)
    )
    records = [head.model_copy(update={"annotator_id": "submitted"})]
    for row in rows:
        identifier = row.approved_revision_id or row.latest_revision_id
        revision = session.get(ProductionRevisionRow, identifier) if identifier else None
        if revision is not None:
            record = AnnotationRevision.model_validate(revision.payload).annotation
            records.append(record.model_copy(update={"annotator_id": "submitted"}))
    return records


def _near_duplicates(
    session: Session, project: Project, records: list[AnnotationRecord]
) -> tuple[NearDuplicatePair, ...]:
    # Only label sets take part in the near-duplicate rule, so box work never decodes images.
    if not records[0].labels or records[0].image_width is None:
        return ()
    keys = sample_keys(session, project)
    threshold = read_near_duplicate().hamming_threshold
    hashes = [
        (item.sample_id, sample_hash(keys[item.sample_id]))
        for item in records
        if item.sample_id in keys
    ]
    own = next((value for sample, value in hashes if sample == records[0].sample_id), None)
    if own is None:
        return ()
    return tuple(
        NearDuplicatePair(sample_id=records[0].sample_id, other_sample_id=sample)
        for sample, value in hashes
        if sample != records[0].sample_id
        and value is not None
        and (own ^ value).bit_count() <= threshold
    )


def _finding_reasons(
    session: Session, project: Project, task: ProductionTaskRow, head: AnnotationRecord
) -> list[RiskReason]:
    records = _context(session, project, task, head)
    batch = AnnotationBatch(
        annotations=tuple(records), near_duplicates=_near_duplicates(session, project, records)
    )
    return [
        finding_reason(item) for item in find_suspicions(batch) if item.sample_id == task.sample_id
    ]


def _disagreement(session: Session, head: AnnotationRevision) -> list[RiskReason]:
    identifier = head.previous_revision_id
    seen: set[str] = set()
    while identifier is not None and identifier not in seen:
        seen.add(identifier)
        row = session.get(ProductionRevisionRow, identifier)
        if row is None:
            return []
        revision = AnnotationRevision.model_validate(row.payload)
        if revision.source == "model":
            difference = prelabel_difference(head.annotation, revision.annotation)
            matched = {
                pair.human_index
                for pair in compare_records(revision.annotation, head.annotation).pairs
            }
            objects = tuple(
                ObjectRef.model_validate({"kind": item.kind, "index": item.position})
                for position, item in enumerate(record_objects(head.annotation))
                if position not in matched
            )
            confidences = object_confidences(revision) or (revision.confidence or 0.0,)
            reason = disagreement_reason(min(confidences), difference, objects)
            return [reason] if reason is not None else []
        identifier = revision.previous_revision_id
    return []


def prereview(
    session: Session, project: Project, task: ProductionTaskRow, head: AnnotationRevision
) -> AIReview:
    """Score the submitted head, decide review or exemption, and store the evidence."""
    reasons = [
        *_template_reasons(session, project, head.annotation),
        *_finding_reasons(session, project, task, head.annotation),
        *(_disagreement(session, head) if head.source == "human" else []),
    ]
    risk = risk_score(reasons)
    draw = sample_draw(task.id, task.round, head.id)
    high = risk >= HIGH_RISK
    rate = project.review_sample_rate
    if project.workflow_tier == "personal":
        decision, note = "personal", ""
    elif high or draw < rate:
        decision, note = "review", ""
    else:
        decision = "exempt"
        note = f"{EXEMPT_NOTE}: sample_rate={rate:.4g}, risk={risk:.4f}, draw={draw:.4f}"
    review = AIReview.model_validate(
        {
            "id": new_id(),
            "project_id": project.id,
            "task_id": task.id,
            "revision_id": head.id,
            "round": task.round,
            "risk": risk,
            "high_risk": high,
            "reasons": reasons,
            "sample_rate": rate,
            "draw": draw,
            "decision": decision,
            "note": note,
            "created_at": utcnow(),
        }
    )
    session.add(
        ProductionAIReviewRow(
            id=review.id,
            task_id=task.id,
            project_id=project.id,
            revision_id=head.id,
            risk=risk,
            payload=review.model_dump(mode="json"),
        )
    )
    if decision == "exempt":
        task.approved_revision_id = task.latest_revision_id
        finish_assignment(session, task.id, "annotation", "approved")
        transition_task(session, task, "approved")
    return review
