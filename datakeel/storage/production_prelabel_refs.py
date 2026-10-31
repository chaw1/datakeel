# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pair each approved human revision with its closest preceding model draft.

These pairs are the only reference set for prelabel accuracy and for calibrating confidence
tiers: unreviewed work and approved model-only revisions never count as human references.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.annotation_qa import compare_records, record_objects
from datakeel.core.production_models import AnnotationRevision
from datakeel.storage.annotation_frames import revision_view
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow


def _preceding_model(
    revisions: dict[str, AnnotationRevision], approved: AnnotationRevision
) -> AnnotationRevision | None:
    identifier = approved.previous_revision_id
    seen: set[str] = set()
    while identifier is not None and identifier not in seen:
        seen.add(identifier)
        revision = revisions.get(identifier)
        if revision is None or revision.task_id != approved.task_id:
            return None
        if revision.source == "model":
            return revision
        identifier = revision.previous_revision_id
    return None


def approved_references(
    session: Session, project_id: str
) -> list[tuple[AnnotationRevision, AnnotationRevision]]:
    """Return (model draft, approved human head) pairs in task identity order.

    Both sides are read upright: legacy stored-frame rows are converted on read.
    """
    revisions = {
        row.id: revision_view(session, row)
        for row in session.scalars(
            select(ProductionRevisionRow).where(ProductionRevisionRow.project_id == project_id)
        )
    }
    tasks = session.scalars(
        select(ProductionTaskRow)
        .where(
            ProductionTaskRow.project_id == project_id,
            ProductionTaskRow.state.in_(("approved", "finalized")),
            ProductionTaskRow.approved_revision_id.is_not(None),
        )
        .order_by(ProductionTaskRow.id)
    )
    references: list[tuple[AnnotationRevision, AnnotationRevision]] = []
    for task in tasks:
        approved = revisions.get(task.approved_revision_id or "")
        if approved is None or approved.source != "human":
            continue
        model = _preceding_model(revisions, approved)
        if model is not None:
            references.append((model, approved))
    return references


def object_confidences(revision: AnnotationRevision) -> tuple[float, ...]:
    """Per-object confidence in canonical order; older drafts repeat the revision value."""
    count = len(record_objects(revision.annotation))
    if len(revision.object_confidences) == count:
        return revision.object_confidences
    return (revision.confidence if revision.confidence is not None else 0.0,) * count


def confidence_observations(
    references: list[tuple[AnnotationRevision, AnnotationRevision]],
) -> list[tuple[float, bool]]:
    """List (confidence, IoU >= 0.5 hit) for every model object with a human reference."""
    result: list[tuple[float, bool]] = []
    for model, human in references:
        hits = compare_records(model.annotation, human.annotation).model_hits()
        result.extend(zip(object_confidences(model), hits, strict=True))
    return result
