# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact indexed workload, confidence and reused annotation agreement measurements."""

from collections import Counter

from sqlalchemy import func, select

from datakeel.annotation_qa import evaluate_annotations, prelabel_accuracy
from datakeel.core.annotation_models import AnnotationBatch, AnnotationQAResult
from datakeel.core.production_models import (
    AnnotatorWorkload,
    ConfidenceBucket,
    ConfidenceDistribution,
    PrelabelAccuracy,
    ProductionWorkload,
)
from datakeel.storage.annotation_frames import revision_view
from datakeel.storage.database import Database
from datakeel.storage.production_prelabel_refs import approved_references
from datakeel.storage.production_rows import (
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_project
from datakeel.storage.workbench_risk import prelabel_difference


def production_prelabel_accuracy(db: Database, project_id: str) -> PrelabelAccuracy:
    """Compare each approved human head with its closest preceding model-source draft.

    ``exact_match_*`` is exact labelled-content agreement, including shape and record
    attributes. ``iou_50``/``iou_75`` match same-label objects one-to-one by descending IoU
    (boxes and polygons by area, spans by character interval, label sets by identity), and
    attribute agreement is reported separately among IoU >= 0.5 matches. Unreviewed tasks and
    approved model-only revisions never serve as human references; absent references yield null.
    """
    with db.session() as session:
        require_project(session, project_id)
        references = [
            (model.annotation, human.annotation)
            for model, human in approved_references(session, project_id)
        ]
    assessed = len(references)
    exact = sum(prelabel_difference(human, model) == 0 for model, human in references)
    iou_50, iou_75, attributes = prelabel_accuracy(references)
    return PrelabelAccuracy(
        project_id=project_id,
        assessed_tasks=assessed,
        exact_match_tasks=exact,
        exact_match_rate=exact / assessed if assessed else None,
        iou_50=iou_50,
        iou_75=iou_75,
        attribute_agreement=attributes,
    )


def annotator_workload(db: Database, project_id: str) -> ProductionWorkload:
    """Count distinct handled tasks, approved tasks and rework decisions per original annotator."""
    with db.session() as session:
        require_project(session, project_id)
        handled: Counter[str] = Counter()
        completed: Counter[str] = Counter()
        for actor, state, count in session.execute(
            select(ProductionTaskRow.annotator_id, ProductionTaskRow.state, func.count())
            .where(ProductionTaskRow.project_id == project_id)
            .group_by(ProductionTaskRow.annotator_id, ProductionTaskRow.state)
        ):
            if actor is not None:
                handled[actor] += count
                if state in {"approved", "finalized"}:
                    completed[actor] += count
        reviews: Counter[str] = Counter()
        reworks: Counter[str] = Counter()
        for actor, decision, count in session.execute(
            select(ProductionReviewRow.annotator_id, ProductionReviewRow.decision, func.count())
            .where(ProductionReviewRow.project_id == project_id)
            .group_by(ProductionReviewRow.annotator_id, ProductionReviewRow.decision)
        ):
            reviews[actor] += count
            if decision == "rework":
                reworks[actor] += count
        return ProductionWorkload(
            project_id=project_id,
            annotators=tuple(
                AnnotatorWorkload(
                    actor=actor,
                    assigned=handled[actor],
                    completed=completed[actor],
                    rework_count=reworks[actor],
                    review_count=reviews[actor],
                    rework_rate=reworks[actor] / reviews[actor] if reviews[actor] else 0,
                )
                for actor in sorted(handled.keys() | reviews.keys())
            ),
        )


def confidence_distribution(db: Database, project_id: str) -> ConfidenceDistribution:
    """Bucket every model revision with a confidence value into ten deterministic intervals."""
    with db.session() as session:
        require_project(session, project_id)
        counts: Counter[int] = Counter()
        for value in session.scalars(
            select(ProductionRevisionRow.confidence).where(
                ProductionRevisionRow.project_id == project_id,
                ProductionRevisionRow.source == "model",
                ProductionRevisionRow.confidence.is_not(None),
            )
        ):
            if value is not None:
                counts[min(int(value * 10), 9)] += 1
        return ConfidenceDistribution(
            project_id=project_id,
            total=sum(counts.values()),
            buckets=tuple(
                ConfidenceBucket(lower=index / 10, upper=(index + 1) / 10, count=counts[index])
                for index in range(10)
            ),
        )


def production_agreement(db: Database, project_id: str) -> AnnotationQAResult:
    """Reuse P26 agreement over the latest saved record of each sample and annotator identity."""
    with db.session() as session:
        require_project(session, project_id)
        revisions = sorted(
            (
                revision_view(session, row)
                for row in session.scalars(
                    select(ProductionRevisionRow).where(
                        ProductionRevisionRow.project_id == project_id
                    )
                )
            ),
            key=lambda item: (item.created_at, item.id),
        )
        records = {
            (item.annotation.sample_id, item.annotation.annotator_id): item.annotation
            for item in revisions
        }
        return evaluate_annotations(AnnotationBatch(annotations=tuple(records.values())))
