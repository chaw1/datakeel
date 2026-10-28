# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Restore standard COCO and YOLO detections without training-library dependencies."""

import math

from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import CocoDataset, YoloDataset, YoloImage

_YOLO_COLUMNS = 5


def validate_box(box: AnnotationBox, width: float, height: float) -> None:
    """Reject boxes outside the decoded image or with empty/reversed extent."""
    if not 0 <= box.x1 < box.x2 <= width or not 0 <= box.y1 < box.y2 <= height:
        message = "Detection boxes must have positive area inside image dimensions"
        raise ValidationError(message)


def _unique(values: list[int | str], description: str) -> None:
    if len(values) != len(set(values)):
        message = f"Duplicate {description} identities"
        raise ValidationError(message)


def import_coco(
    document: CocoDataset, annotator_id: str, sample_ids: dict[str, str] | None = None
) -> tuple[AnnotationRecord, ...]:
    """Restore xyxy records from a complete COCO dataset, including empty images.

    An explicit filename-to-source-identity map takes precedence over the optional
    Datakeel extension. External COCO can instead use filenames as sample identities.
    """
    _unique([image.id for image in document.images], "COCO image")
    _unique([category.id for category in document.categories], "COCO category")
    _unique([box.id for box in document.annotations], "COCO annotation")
    images = {image.id: image for image in document.images}
    categories = {category.id: category.name for category in document.categories}
    boxes: dict[int, list[AnnotationBox]] = {identifier: [] for identifier in images}
    for item in document.annotations:
        if item.image_id not in images or item.category_id not in categories:
            message = "COCO annotation references an unknown image or category"
            raise ValidationError(message)
        x, y, width, height = item.bbox
        box = AnnotationBox(
            category=categories[item.category_id], x1=x, y1=y, x2=x + width, y2=y + height
        )
        image = images[item.image_id]
        validate_box(box, image.width, image.height)
        boxes[item.image_id].append(box)
    records = tuple(
        AnnotationRecord(
            sample_id=(sample_ids or {}).get(
                image.file_name, image.datakeel_sample_id or image.file_name
            ),
            annotator_id=annotator_id,
            labels=tuple(sorted({box.category for box in boxes[image.id]})),
            boxes=tuple(boxes[image.id]),
            image_width=image.width,
            image_height=image.height,
        )
        for image in document.images
    )
    _unique([record.sample_id for record in records], "source sample")
    return records


def _yolo_boxes(image: YoloImage, names: tuple[str, ...]) -> tuple[AnnotationBox, ...]:
    boxes: list[AnnotationBox] = []
    for line in image.labels.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != _YOLO_COLUMNS:
            message = "YOLO detection rows require class and four normalized coordinates"
            raise ValidationError(message)
        try:
            category = int(fields[0])
            x, y, width, height = (float(value) for value in fields[1:])
        except ValueError as error:
            message = "Invalid YOLO class or coordinate"
            raise ValidationError(message) from error
        if not 0 <= category < len(names) or not all(
            math.isfinite(value) and 0 <= value <= 1 for value in (x, y, width, height)
        ):
            message = "YOLO class or normalized coordinates are outside their valid range"
            raise ValidationError(message)
        box = AnnotationBox(
            category=names[category],
            x1=(x - width / 2) * image.width,
            y1=(y - height / 2) * image.height,
            x2=(x + width / 2) * image.width,
            y2=(y + height / 2) * image.height,
        )
        validate_box(box, image.width, image.height)
        boxes.append(box)
    return tuple(boxes)


def import_yolo(document: YoloDataset, annotator_id: str) -> tuple[AnnotationRecord, ...]:
    """Restore source-pixel boxes from normalized zero-indexed YOLO text labels."""
    _unique([image.sample_id for image in document.images], "YOLO image")
    _unique(list(document.names), "YOLO category")
    records: list[AnnotationRecord] = []
    for image in document.images:
        boxes = _yolo_boxes(image, document.names)
        records.append(
            AnnotationRecord(
                sample_id=image.sample_id,
                annotator_id=annotator_id,
                boxes=boxes,
                labels=tuple(sorted({box.category for box in boxes})),
                image_width=image.width,
                image_height=image.height,
            )
        )
    return tuple(records)
