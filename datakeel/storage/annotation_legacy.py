# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Adapt existing COCO sidecar and operator metadata models to multi-annotator review."""

from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.models import FileItem
from datakeel.operators.evidence.annotation_labels import CocoDocument
from datakeel.operators.evidence.facts import annotation_facts


def annotation_from_coco(
    sample_id: str, annotator_id: str, document: CocoDocument
) -> AnnotationRecord:
    """Convert existing COCO xywh boxes without reinterpreting them as xyxy coordinates."""
    boxes = tuple(
        AnnotationBox(
            category=item.category,
            x1=item.bbox[0],
            y1=item.bbox[1],
            x2=item.bbox[0] + item.bbox[2],
            y2=item.bbox[1] + item.bbox[3],
        )
        for item in document.annotations
    )
    return AnnotationRecord(
        sample_id=sample_id,
        annotator_id=annotator_id,
        labels=tuple(sorted({box.category for box in boxes})),
        boxes=boxes,
        image_width=document.width,
        image_height=document.height,
    )


def annotation_from_file(file: FileItem, annotator_id: str) -> AnnotationRecord:
    """Preserve existing annotation availability, concept labels and source-pixel xyxy boxes."""
    facts = annotation_facts(file)
    boxes = tuple(
        AnnotationBox(
            category=item.concept,
            x1=item.bbox[0],
            y1=item.bbox[1],
            x2=item.bbox[2],
            y2=item.bbox[3],
        )
        for item in facts.annotation_boxes
    )
    first = next(iter(facts.annotation_boxes), None)
    return AnnotationRecord(
        sample_id=file.id,
        annotator_id=annotator_id,
        labels=facts.annotation_categories if facts.annotation_available else None,
        boxes=boxes if facts.annotation_available else None,
        image_width=first.width if first else None,
        image_height=first.height if first else None,
    )
