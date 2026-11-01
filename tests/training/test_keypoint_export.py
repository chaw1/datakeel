# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent COCO oracle, native round trips and explicit keypoint format protections."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from datakeel.core.annotation_models import (
    AnnotationBox,
    AnnotationKeypoint,
    AnnotationRecord,
    AnnotationSkeleton,
)
from datakeel.core.errors import ValidationError
from datakeel.core.keypoint_models import KeypointDefinition, SkeletonDefinition
from datakeel.core.models import FileItem
from datakeel.core.production_catalog_models import LabelSet, PredictionFile, ProductionLabel
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.core.training_export_models import (
    CocoDataset,
    TrainingExport,
    TrainingExportItem,
    TrainingFormat,
)
from datakeel.storage.production_prediction_parsing import parse_coco
from datakeel.training.export import write_training_export
from datakeel.training.importers import import_coco
from datakeel.training.native import import_annotations_jsonl


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except ValidationError as error:
        message = str(error)
    if message is None:
        text = "Expected keypoint format protection to reject the operation"
        raise AssertionError(text)
    assert match in message


def _schema() -> SkeletonDefinition:
    return SkeletonDefinition(
        points=(
            KeypointDefinition(id="nose", name="Nose", required=True),
            KeypointDefinition(id="neck", name="Neck"),
            KeypointDefinition(id="wrist", name="Wrist"),
        ),
        edges=(("nose", "neck"), ("neck", "wrist")),
    )


def _export(tmp_path: Path, format_name: TrainingFormat = "coco") -> TrainingExport:
    source = tmp_path / "source.png"
    Image.new("RGB", (100, 80)).save(source)
    content = source.read_bytes()
    file = FileItem(
        id="image",
        path=str(source),
        filename=source.name,
        modality="image",
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )
    annotation = AnnotationRecord(
        sample_id="image",
        annotator_id="ann",
        boxes=(AnnotationBox(category="box-only", x1=1, y1=2, x2=11, y2=22),),
        keypoints=(
            AnnotationSkeleton(
                category="person",
                points=(
                    AnnotationKeypoint(id="wrist", state="missing"),
                    AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
                    AnnotationKeypoint(id="neck", x=30, y=40, state="occluded"),
                ),
                attributes={"side": "left"},
            ),
        ),
        image_width=100,
        image_height=80,
    )
    return TrainingExport(
        dataset_id="d",
        version_id="v",
        split_set_id="s",
        seed=1,
        format=format_name,
        items=(TrainingExportItem(file=file, split="train", annotation=annotation),),
        keypoint_schema=_schema(),
    )


def _write(export: TrainingExport, directory: Path) -> Path:
    package = directory / "package"
    write_training_export(export, package, directory / "export.tar")
    return package


def test_coco_matches_an_independent_keypoint_oracle(tmp_path: Path) -> None:
    """Raw JSON matches independently specified order, visibility, bbox and topology."""
    package = _write(_export(tmp_path), tmp_path / "coco")
    raw = json.loads((package / "annotations/instances_train.json").read_text())
    assert raw["categories"] == [
        {"id": 1, "name": "box-only", "supercategory": ""},
        {
            "id": 2,
            "name": "person",
            "supercategory": "",
            "keypoints": ["Nose", "Neck", "Wrist"],
            "skeleton": [[1, 2], [2, 3]],
        },
    ]
    [box, pose] = raw["annotations"]
    assert "keypoints" not in box
    assert "num_keypoints" not in box
    assert pose["keypoints"] == [10, 20, 2, 30, 40, 1, 0, 0, 0]
    assert pose["num_keypoints"] == 2
    assert pose["bbox"] == [10, 20, 20, 20]
    assert pose["area"] == 400
    assert pose["attributes"] == {"side": "left"}


def test_single_visible_point_has_zero_area_keypoint_bbox(tmp_path: Path) -> None:
    """A one-point pose keeps a legal zero-area COCO bbox."""
    export = _export(tmp_path)
    item = export.items[0]
    skeletons = item.annotation.keypoints or ()
    skeleton = skeletons[0].model_copy(
        update={
            "points": (
                AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
                AnnotationKeypoint(id="neck", state="missing"),
                AnnotationKeypoint(id="wrist", state="missing"),
            )
        }
    )
    annotation = item.annotation.model_copy(update={"keypoints": (skeleton,)})
    package = _write(
        export.model_copy(update={"items": (item.model_copy(update={"annotation": annotation}),)}),
        tmp_path / "single",
    )
    raw = json.loads((package / "annotations/instances_train.json").read_text())
    assert raw["annotations"][-1]["bbox"] == [10, 20, 0, 0]
    assert raw["annotations"][-1]["area"] == 0
    assert raw["annotations"][-1]["num_keypoints"] == 1


def test_native_jsonl_exactly_roundtrips_skeleton_content(tmp_path: Path) -> None:
    """Native export/import retains IDs, input order, states, coordinates and attributes."""
    export = _export(tmp_path, "annotations_jsonl")
    package = _write(export, tmp_path / "native")
    rows = (package / "annotations.jsonl").read_text()
    assert import_annotations_jsonl(rows) == (export.items[0].annotation,)
    raw = json.loads(rows)
    assert [point["id"] for point in raw["keypoints"][0]["points"]] == [
        "wrist",
        "nose",
        "neck",
    ]
    assert raw["keypoints"][0]["attributes"] == {"side": "left"}


def test_coco_requires_schema_but_native_jsonl_does_not(tmp_path: Path) -> None:
    """Schema-dependent COCO fails clearly while lossless native export still works."""
    export = _export(tmp_path).model_copy(update={"keypoint_schema": None})
    with pytest.raises(ValidationError, match="locked keypoint schema"):
        _write(export, tmp_path / "bad-coco")
    package = _write(
        export.model_copy(update={"format": "annotations_jsonl"}), tmp_path / "native-no-schema"
    )
    assert import_annotations_jsonl((package / "annotations.jsonl").read_text())


@pytest.mark.parametrize("format_name", ["yolo", "imagefolder", "hf_imagefolder", "text_jsonl"])
def test_unsupported_formats_reject_instead_of_dropping_keypoints(
    tmp_path: Path, format_name: TrainingFormat
) -> None:
    """Every non-keypoint format rejects nonempty skeleton content."""
    _reject(
        lambda: _write(_export(tmp_path, format_name), tmp_path / format_name),
        "does not support keypoints",
    )


def test_coco_keypoint_import_is_explicitly_rejected_even_with_bbox(tmp_path: Path) -> None:
    """COCO poses cannot silently turn into detection boxes."""
    package = _write(_export(tmp_path), tmp_path / "coco")
    document = CocoDataset.model_validate_json(
        (package / "annotations/instances_train.json").read_bytes()
    )
    _reject(lambda: import_coco(document, "ann"), "annotations_jsonl")


def test_coco_keypoint_archives_are_byte_stable(tmp_path: Path) -> None:
    """Repeated keypoint exports produce identical archive bytes."""
    export = _export(tmp_path)
    _write(export, tmp_path / "first")
    _write(export, tmp_path / "second")
    assert (tmp_path / "first/export.tar").read_bytes() == (
        tmp_path / "second/export.tar"
    ).read_bytes()


def test_prediction_coco_keypoints_fail_instead_of_becoming_boxes() -> None:
    """The production prediction importer applies the same explicit keypoint protection."""
    document = {
        "images": [{"id": 1, "file_name": "image.png", "width": 100, "height": 80}],
        "categories": [{"id": 1, "name": "person", "keypoints": ["Nose"]}],
        "annotations": [
            {
                "image_id": 1,
                "category_id": 1,
                "bbox": [1, 2, 30, 40],
                "keypoints": [10, 20, 2],
                "num_keypoints": 1,
            }
        ],
    }
    labels = LabelSet(
        id="labels",
        version=1,
        name="Labels",
        labels=(ProductionLabel(id="person", name="person"),),
        published=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = parse_coco(
        PredictionFile(filename="pose.json", content=json.dumps(document)),
        labels,
        {},
        (PredictionSample(id="image", filename="image.png", width=100, height=80),),
    )
    assert not result.predictions
    assert [failure.code for failure in result.failures] == ["unsupported_keypoints"]
