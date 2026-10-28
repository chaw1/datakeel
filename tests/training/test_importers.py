# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject malformed training formats while preserving external category and image identities."""

import math

import pytest
from pydantic import ValidationError as SchemaError

from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import (
    CocoBox,
    CocoCategory,
    CocoDataset,
    CocoImage,
    TrainingAnnotationImport,
    YoloDataset,
    YoloImage,
)
from datakeel.training.importers import import_coco, import_yolo


def _coco() -> CocoDataset:
    return CocoDataset(
        images=(CocoImage(id=91, file_name="source.png", width=100, height=80),),
        annotations=(CocoBox(id=12, image_id=91, category_id=7, bbox=(0, 0, 100, 80)),),
        categories=(CocoCategory(id=7, name="cat"),),
    )


def test_external_coco_uses_category_ids_and_explicit_source_map() -> None:
    """Sparse category identities and extra standard COCO keys do not change detections."""
    document = CocoDataset.model_validate(
        {
            **_coco().model_dump(),
            "info": {"description": "generated"},
            "licenses": [],
        }
    )
    record = import_coco(document, "r", {"source.png": "source-id"})[0]
    assert record.sample_id == "source-id"
    assert record.boxes is not None
    assert record.boxes[0].category == "cat"
    assert record.boxes[0].x2 == 100
    assert record.boxes[0].y2 == 80


@pytest.mark.parametrize("field", ["images", "categories", "annotations"])
def test_coco_rejects_duplicate_identities(field: str) -> None:
    """Dictionary construction must never silently discard a duplicate image or annotation."""
    document = _coco()
    values = getattr(document, field)
    with pytest.raises(ValidationError, match="Duplicate"):
        import_coco(document.model_copy(update={field: (*values, *values)}), "r")


@pytest.mark.parametrize(("field", "value"), [("image_id", 8), ("category_id", 8)])
def test_coco_rejects_dangling_reference(field: str, value: int) -> None:
    """Unknown references fail instead of dropping annotations silently."""
    document = _coco()
    with pytest.raises(ValidationError, match="unknown image or category"):
        import_coco(
            document.model_copy(
                update={"annotations": (document.annotations[0].model_copy(update={field: value}),)}
            ),
            "r",
        )


@pytest.mark.parametrize(
    "row",
    [
        "0 0.5 0.5 1",
        "cat 0.5 0.5 1 1",
        "2 0.5 0.5 1 1",
        "0 nan 0.5 1 1",
        "0 0.5 0.5 0 1",
        "0 0.1 0.5 1 1",
        "0 0.5 0.5 -1 1",
        "0.0 0.5 0.5 1 1",
    ],
)
def test_yolo_rejects_malformed_or_out_of_bounds_rows(row: str) -> None:
    """YOLO is exactly class plus four finite normalized coordinates with positive extent."""
    with pytest.raises(ValidationError):
        import_yolo(
            YoloDataset(
                names=("cat",), images=(YoloImage(sample_id="a", width=100, height=80, labels=row),)
            ),
            "r",
        )


def test_yolo_empty_label_file_is_a_reviewed_empty_annotation() -> None:
    """Images with no detections must survive both export and import."""
    record = import_yolo(
        YoloDataset(
            names=("cat",), images=(YoloImage(sample_id="a", width=100, height=80, labels="\n"),)
        ),
        "r",
    )[0]
    assert record.boxes == ()
    assert record.labels == ()


def test_import_request_accepts_only_one_document_matching_format() -> None:
    """Typed HTTP import contracts reject mismatched or conflicting payload formats."""
    with pytest.raises(SchemaError, match="matching"):
        TrainingAnnotationImport(format="yolo", idempotency_key="a", coco=_coco())
    assert TrainingAnnotationImport(format="coco", idempotency_key="a", coco=_coco()).coco


@pytest.mark.parametrize("overflow", [1e-8, 1.0])
def test_coco_rejects_real_overflow_after_restoring_xywh(overflow: float) -> None:
    """The restoration tolerance must never hide a meaningful box error."""
    document = _coco()
    annotation = document.annotations[0].model_copy(update={"bbox": (0, 0, 100 + overflow, 80)})
    with pytest.raises(ValidationError, match="inside image"):
        import_coco(document.model_copy(update={"annotations": (annotation,)}), "r")


def test_coco_restoration_accepts_only_few_ulp_boundary_noise() -> None:
    """A coordinate produced by adding xywh extents can be restored to the exact image edge."""
    document = _coco()
    annotation = document.annotations[0].model_copy(
        update={"bbox": (0, 0, math.nextafter(100.0, math.inf), 80)}
    )
    record = import_coco(document.model_copy(update={"annotations": (annotation,)}), "r")[0]
    assert record.boxes is not None
    assert record.boxes[0].x2 == 100


def test_yolo_restoration_clamps_few_ulp_negative_edge_only() -> None:
    """A one-ULP normalized subtraction error is safe; an actually negative box stays invalid."""
    document = YoloDataset(
        names=("cat",),
        images=(
            YoloImage(
                sample_id="a", width=100, height=80, labels="0 0.1 0.5 0.20000000000000004 1"
            ),
        ),
    )
    record = import_yolo(document, "r")[0]
    assert record.boxes is not None
    assert record.boxes[0].x1 == 0
    bad = document.images[0].model_copy(update={"labels": "0 0.1 0.5 0.200000001 1"})
    with pytest.raises(ValidationError, match="inside image"):
        import_yolo(document.model_copy(update={"images": (bad,)}), "r")
