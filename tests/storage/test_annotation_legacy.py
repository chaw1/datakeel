# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Existing COCO sidecars and evidence facts convert to review records unchanged."""

from datakeel.core.annotation_models import AnnotationBox
from datakeel.core.models import FileItem
from datakeel.operators.evidence.annotation_labels import CocoAnnotation, CocoDocument
from datakeel.storage.annotation_legacy import annotation_from_coco, annotation_from_file


def test_coco_xywh_boxes_become_xyxy_with_image_size() -> None:
    """COCO width/height offsets are added once, and categories become the label set."""
    document = CocoDocument(
        annotations=(
            CocoAnnotation(category="ship", bbox=(10, 20, 30, 40)),
            CocoAnnotation(category="buoy", bbox=(0, 0, 5, 5)),
        ),
        width=128,
        height=96,
    )
    record = annotation_from_coco("file-1", "reviewer", document)
    assert record.boxes == (
        AnnotationBox(category="ship", x1=10, y1=20, x2=40, y2=60),
        AnnotationBox(category="buoy", x1=0, y1=0, x2=5, y2=5),
    )
    assert record.labels == ("buoy", "ship")
    assert (record.image_width, record.image_height) == (128, 96)


def test_file_facts_keep_missing_and_known_empty_annotations_apart() -> None:
    """Unannotated files stay missing; evidence boxes keep their source-pixel xyxy form."""
    missing = annotation_from_file(FileItem(path="a.png", filename="a.png"), "reviewer")
    assert (missing.labels, missing.boxes) == (None, None)
    annotated = FileItem(
        path="b.png",
        filename="b.png",
        metadata={
            "annotation_available": True,
            "annotation_categories": ["ship"],
            "annotation_boxes": [
                {"concept": "ship", "bbox": [1, 2, 3, 4], "width": 64, "height": 48}
            ],
        },
    )
    record = annotation_from_file(annotated, "reviewer")
    assert record.labels == ("ship",)
    assert record.boxes == (AnnotationBox(category="ship", x1=1, y1=2, x2=3, y2=4),)
    assert (record.image_width, record.image_height) == (64, 48)
