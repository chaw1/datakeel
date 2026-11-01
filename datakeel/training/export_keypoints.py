# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialize native skeleton instances into explicit, template-bound COCO keypoint records."""

from datakeel.core.annotation_models import AnnotationSkeleton
from datakeel.core.errors import ValidationError
from datakeel.core.keypoint_models import SkeletonDefinition
from datakeel.core.training_export_models import CocoBox, TrainingExport


def has_keypoints(export: TrainingExport) -> bool:
    """Report whether any item contains at least one native skeleton instance."""
    return any(item.annotation.keypoints for item in export.items)


def require_no_keypoints(export: TrainingExport, format_name: str) -> None:
    """Prevent formats without a keypoint representation from silently dropping skeletons."""
    if has_keypoints(export):
        message = f"{format_name} does not support keypoints; use coco or annotations_jsonl"
        raise ValidationError(message)


def export_schema(export: TrainingExport) -> SkeletonDefinition | None:
    """Require the finalized project's locked schema whenever native skeletons are present."""
    if has_keypoints(export) and export.keypoint_schema is None:
        message = "COCO keypoint export requires the finalized project's locked keypoint schema"
        raise ValidationError(message)
    return export.keypoint_schema


def skeleton_category_names(export: TrainingExport) -> set[str]:
    """List categories that need COCO keypoint topology metadata."""
    return {
        skeleton.category for item in export.items for skeleton in item.annotation.keypoints or ()
    }


def coco_edges(schema: SkeletonDefinition) -> tuple[tuple[int, int], ...]:
    """Translate stable edge endpoint IDs to COCO's one-based template positions."""
    positions = {point.id: index for index, point in enumerate(schema.points, 1)}
    return tuple((positions[left], positions[right]) for left, right in schema.edges)


def coco_skeleton(
    skeleton: AnnotationSkeleton,
    *,
    annotation_id: int,
    image_id: int,
    category_id: int,
    schema: SkeletonDefinition | None,
) -> CocoBox:
    """Convert one skeleton using schema order, COCO visibility and a non-missing-point bbox."""
    if schema is None:
        message = "COCO keypoint export requires a locked schema"
        raise ValidationError(message)
    by_id = {point.id: point for point in skeleton.points}
    if len(by_id) != len(skeleton.points):
        message = "COCO keypoint export rejects duplicate point identities"
        raise ValidationError(message)
    known = {point.id for point in schema.points}
    if not set(by_id) <= known:
        message = "COCO keypoint export rejects points absent from the locked schema"
        raise ValidationError(message)
    values: list[float] = []
    positioned: list[tuple[float, float]] = []
    for definition in schema.points:
        point = by_id.get(definition.id)
        if point is None or point.state == "missing":
            values.extend((0.0, 0.0, 0.0))
            continue
        if point.x is None or point.y is None:
            message = "Positioned keypoints require coordinates"
            raise ValidationError(message)
        values.extend((point.x, point.y, 2.0 if point.state == "visible" else 1.0))
        positioned.append((point.x, point.y))
    if not positioned:
        message = "COCO keypoint export requires at least one positioned point per skeleton"
        raise ValidationError(message)
    xs, ys = tuple(point[0] for point in positioned), tuple(point[1] for point in positioned)
    bbox = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return CocoBox(
        id=annotation_id,
        image_id=image_id,
        category_id=category_id,
        bbox=bbox,
        area=bbox[2] * bbox[3],
        iscrowd=0,
        attributes=skeleton.attributes,
        keypoints=tuple(values),
        num_keypoints=len(positioned),
    )
