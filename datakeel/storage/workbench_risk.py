# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive reviewer ordering from immutable revisions rather than storing another score."""

import json
from collections import Counter, defaultdict
from collections.abc import Sequence

from sqlalchemy import select

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.production_models import AnnotationRevision, ProductionTask
from datakeel.core.workbench_models import WorkbenchTaskRisk
from datakeel.storage.annotation_frames import revision_view
from datakeel.storage.database import Database
from datakeel.storage.production_rows import ProductionRevisionRow


def _atoms(annotation: AnnotationRecord) -> Counter[str]:
    payload = annotation.model_dump(mode="json")
    atoms = Counter(
        json.dumps((kind, value), sort_keys=True, ensure_ascii=False)
        for kind in ("labels", "boxes", "polygons", "spans")
        for value in payload.get(kind) or ()
    )
    for kind in ("labels", "boxes", "polygons", "spans"):
        if payload.get(kind) == []:
            atoms[json.dumps((kind, []))] += 1
    if annotation.attributes:
        atoms[json.dumps(("attributes", annotation.attributes), sort_keys=True)] += 1
    return atoms


def prelabel_difference(human: AnnotationRecord, model: AnnotationRecord) -> float:
    """Return one minus multiset Jaccard agreement over labelled content and attributes.

    Provenance is excluded; shape attributes and exact source coordinates are retained.
    Two reviewed-empty results agree. This is a transparent review-priority signal,
    not an estimate of model accuracy against a human-reviewed reference set.
    """
    left, right = _atoms(human), _atoms(model)
    union = left | right
    return 1 - sum((left & right).values()) / sum(union.values()) if union else 0.0


def task_risks(db: Database, tasks: Sequence[ProductionTask]) -> tuple[WorkbenchTaskRisk, ...]:
    """Compare each saved human head with the latest model-source revision on its own task."""
    if not tasks:
        return ()
    revisions: dict[str, list[AnnotationRevision]] = defaultdict(list)
    with db.session() as session:
        for row in session.scalars(
            select(ProductionRevisionRow).where(
                ProductionRevisionRow.task_id.in_(tuple(task.id for task in tasks))
            )
        ):
            revisions[row.task_id].append(revision_view(session, row))
    result: list[WorkbenchTaskRisk] = []
    for task in tasks:
        ordered = sorted(revisions[task.id], key=lambda item: (item.created_at, item.id))
        head = next((item for item in ordered if item.id == task.latest_revision_id), None)
        model = next((item for item in reversed(ordered) if item.source == "model"), None)
        difference = (
            prelabel_difference(head.annotation, model.annotation)
            if head is not None and head.source == "human" and model is not None
            else None
        )
        result.append(
            WorkbenchTaskRisk(
                task_id=task.id,
                prelabel_difference=difference,
                model_confidence=model.confidence if model else None,
            )
        )
    return tuple(result)


def review_order(
    tasks: Sequence[ProductionTask], risks: Sequence[WorkbenchTaskRisk]
) -> tuple[ProductionTask, ...]:
    """Prioritize rework rounds, lower model confidence, then greater prelabel differences."""
    differences = {risk.task_id: risk.prelabel_difference or 0.0 for risk in risks}
    confidences = {risk.task_id: risk.model_confidence for risk in risks}
    return tuple(
        sorted(
            tasks,
            key=lambda task: (
                -task.round,
                confidences[task.id]
                if confidences[task.id] is not None
                else task.confidence
                if task.confidence is not None
                else 1.0,
                -differences[task.id],
                task.id,
            ),
        )
    )
