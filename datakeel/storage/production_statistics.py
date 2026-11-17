# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact indexed workload, confidence and reused annotation agreement measurements."""

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import func, select

from datakeel.annotation_qa import comparable_records, evaluate_annotations, prelabel_accuracy
from datakeel.core import production_models as pm
from datakeel.core.annotation_models import AgreementValue, AnnotationBatch, AnnotationQAResult
from datakeel.storage import production_rows as rows
from datakeel.storage.annotation_frames import revision_view
from datakeel.storage.database import Database
from datakeel.storage.production_prelabel_refs import approved_references
from datakeel.storage.production_tasks import require_project
from datakeel.storage.workbench_risk import prelabel_difference

ReviewWindow = tuple[datetime | None, datetime | None, bool]


def production_prelabel_accuracy(db: Database, project_id: str) -> pm.PrelabelAccuracy:
    """Compare each approved human head with its closest preceding model-source draft."""
    with db.session() as session:
        require_project(session, project_id)
        pairs = list(approved_references(session, project_id))
        references = [
            (m.annotation, h.annotation)
            for m, h in pairs
            if comparable_records(m.annotation, h.annotation)
        ]
    assessed = len(references)
    exact = sum(prelabel_difference(human, model) == 0 for model, human in references)
    iou_50, iou_75, attributes = prelabel_accuracy(references)
    kp = AgreementValue(value=None, reason="Keypoint accuracy is not supported")
    seg = AgreementValue(value=None, reason="Segment accuracy is not supported")
    return pm.PrelabelAccuracy(
        project_id=project_id,
        assessed_tasks=assessed,
        exact_match_tasks=exact,
        exact_match_rate=exact / assessed if assessed else None,
        iou_50=iou_50,
        iou_75=iou_75,
        attribute_agreement=attributes,
        keypoint_accuracy=kp
        if any(m.annotation.keypoints or h.annotation.keypoints for m, h in pairs)
        else None,
        segment_accuracy=seg
        if any(m.annotation.segments or h.annotation.segments for m, h in pairs)
        else None,
    )


def _in_window(payload: Mapping[str, object], bounds: ReviewWindow) -> bool:
    raw = payload.get("created_at")
    if not isinstance(raw, str):
        return False
    since, until, ex = bounds
    ts = datetime.fromisoformat(raw)
    created = ts.astimezone(UTC) if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    return (since is None or created >= since) and (
        until is None or (created < until if ex else created <= until)
    )


def annotator_workload(
    db: Database, project_id: str, bounds: ReviewWindow | None = None
) -> pm.ProductionWorkload:
    """Count distinct handled tasks, approved tasks and rework decisions per original annotator."""
    with db.session() as session:
        require_project(session, project_id)
        handled, completed = Counter[str](), Counter[str]()
        task_q = (
            select(rows.ProductionTaskRow.annotator_id, rows.ProductionTaskRow.state, func.count())
            .where(rows.ProductionTaskRow.project_id == project_id)
            .group_by(rows.ProductionTaskRow.annotator_id, rows.ProductionTaskRow.state)
        )
        for actor, state, count in session.execute(task_q):
            if actor is not None:
                handled[actor] += count
                completed[actor] += count if state in {"approved", "finalized"} else 0
        reviews, reworks = Counter[str](), Counter[str]()
        if bounds is None or bounds[:2] == (None, None):
            rev_q = (
                select(
                    rows.ProductionReviewRow.annotator_id,
                    rows.ProductionReviewRow.decision,
                    func.count(),
                )
                .where(rows.ProductionReviewRow.project_id == project_id)
                .group_by(rows.ProductionReviewRow.annotator_id, rows.ProductionReviewRow.decision)
            )
            for actor, decision, count in session.execute(rev_q):
                reviews[actor] += count
                reworks[actor] += count if decision == "rework" else 0
        else:
            raw_q = select(
                rows.ProductionReviewRow.annotator_id,
                rows.ProductionReviewRow.decision,
                rows.ProductionReviewRow.payload,
            ).where(rows.ProductionReviewRow.project_id == project_id)
            for actor, decision, payload in session.execute(raw_q):
                if _in_window(payload, bounds):
                    reviews[actor] += 1
                    reworks[actor] += 1 if decision == "rework" else 0
        items = tuple(
            pm.AnnotatorWorkload(
                actor=a,
                assigned=handled[a],
                completed=completed[a],
                rework_count=reworks[a],
                review_count=reviews[a],
                rework_rate=reworks[a] / reviews[a] if reviews[a] else 0,
            )
            for a in sorted(handled.keys() | reviews.keys())
        )
        return pm.ProductionWorkload(project_id=project_id, annotators=items)


def confidence_distribution(db: Database, project_id: str) -> pm.ConfidenceDistribution:
    """Bucket every model revision with a confidence value into ten deterministic intervals."""
    with db.session() as session:
        require_project(session, project_id)
        counts = Counter[int]()
        stmt = select(rows.ProductionRevisionRow.confidence).where(
            rows.ProductionRevisionRow.project_id == project_id,
            rows.ProductionRevisionRow.source == "model",
            rows.ProductionRevisionRow.confidence.is_not(None),
        )
        for value in session.scalars(stmt):
            if value is not None:
                counts[min(int(value * 10), 9)] += 1
        buckets = tuple(
            pm.ConfidenceBucket(lower=i / 10, upper=(i + 1) / 10, count=counts[i])
            for i in range(10)
        )
        return pm.ConfidenceDistribution(
            project_id=project_id, total=sum(counts.values()), buckets=buckets
        )


def production_agreement(db: Database, project_id: str) -> AnnotationQAResult:
    """Reuse P26 agreement over the latest saved record of each sample and annotator identity."""
    with db.session() as session:
        require_project(session, project_id)
        stmt = select(rows.ProductionRevisionRow).where(
            rows.ProductionRevisionRow.project_id == project_id
        )
        revs = sorted(
            (revision_view(session, r) for r in session.scalars(stmt)),
            key=lambda x: (x.created_at, x.id),
        )
        records = {
            (item.annotation.sample_id, item.annotation.annotator_id): item.annotation
            for item in revs
        }
        return evaluate_annotations(AnnotationBatch(annotations=tuple(records.values())))
