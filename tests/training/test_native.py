# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lossless native annotation interchange preserves all four component representations."""

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import CocoDataset, TrainingAnnotationImport
from datakeel.training.importers import import_coco
from datakeel.training.native import import_annotations_jsonl
from tests.workbench_helpers import ComponentKind, annotation_for


@pytest.mark.parametrize("kind", ["box", "polygon", "classification", "text_span"])
def test_native_jsonl_preserves_nullable_components_properties_and_exact_geometry(
    kind: ComponentKind,
) -> None:
    """Core JSON records round-trip without converting empty annotations or typed properties."""
    annotation = annotation_for(kind, "sample")
    restored = import_annotations_jsonl(annotation.model_dump_json() + "\n")
    assert restored == (annotation,)
    empty = annotation.model_copy(update={"labels": (), "boxes": (), "polygons": (), "spans": ()})
    assert import_annotations_jsonl(empty.model_dump_json()) == (empty,)


def test_native_jsonl_rejects_empty_and_duplicate_identities() -> None:
    """Interchange never silently drops duplicated sample/annotator work or imports no records."""
    annotation = annotation_for("polygon", "sample")
    with pytest.raises(ValidationError, match="nonempty"):
        import_annotations_jsonl("\n")
    with pytest.raises(ValidationError, match="distinct"):
        import_annotations_jsonl(annotation.model_dump_json() + "\n" + annotation.model_dump_json())
    request = TrainingAnnotationImport(
        format="annotations_jsonl",
        idempotency_key="native",
        annotations_jsonl=annotation.model_dump_json(),
    )
    assert request.annotations_jsonl is not None


def test_coco_import_retains_box_attributes_alongside_standard_coordinates() -> None:
    """Ordinary detection interchange also retains explicit per-box attributes when supplied."""
    document = CocoDataset.model_validate(
        {
            "images": [{"id": 1, "file_name": "sample.png", "width": 100, "height": 80}],
            "categories": [{"id": 1, "name": "cat"}],
            "annotations": [
                {
                    "id": 1,
                    "image_id": 1,
                    "category_id": 1,
                    "bbox": [1, 2, 30, 40],
                    "attributes": {"visible": True, "parts": ["tail", "ear"]},
                }
            ],
        }
    )
    record = import_coco(document, "person")[0]
    assert record.boxes is not None
    assert record.boxes[0].attributes == {"visible": True, "parts": ["tail", "ear"]}
    assert record.boxes[0].x2 == 31
