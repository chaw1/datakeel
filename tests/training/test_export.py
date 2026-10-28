# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate actual training layouts, annotations, source integrity and deterministic bytes."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

import pytest
import yaml
from PIL import Image
from pydantic import ValidationError as SchemaValidationError

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord, AnnotationSpan
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import (
    CocoDataset,
    TrainingExport,
    TrainingExportItem,
    TrainingFormat,
    YoloDataset,
    YoloImage,
)
from datakeel.training.export import write_training_export
from datakeel.training.export_common import class_directory, filename
from datakeel.training.importers import import_coco, import_yolo


def _file(path: Path, identifier: str, modality: str) -> FileItem:
    content = path.read_bytes()
    return FileItem(
        id=identifier,
        path=str(path),
        filename=path.name,
        modality=modality,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


@pytest.fixture
def export(tmp_path: Path) -> TrainingExport:
    """Generate images with absolute boxes, a reviewed-empty image and all three splits."""
    items: list[TrainingExportItem] = []
    for ordinal, split in enumerate(("train", "val", "test")):
        source = tmp_path / f"source-{ordinal}.png"
        Image.new("RGB", (100, 80), (ordinal * 20, 100, 200)).save(source)
        identity = f"image-{ordinal}"
        annotation = AnnotationRecord(
            sample_id=identity,
            annotator_id="reviewer",
            labels=("cat/rare",),
            boxes=(AnnotationBox(category="cat/rare", x1=10, y1=20, x2=40, y2=60),)
            if ordinal != 2
            else (),
            image_width=100,
            image_height=80,
        )
        items.append(
            TrainingExportItem(
                file=_file(source, identity, "image"),
                split=split,
                annotation=annotation,
            )
        )
    return TrainingExport(
        dataset_id="dataset",
        version_id="version",
        split_set_id="split",
        seed=42,
        format="coco",
        items=tuple(items),
    )


def _write(export: TrainingExport, directory: Path) -> Path:
    archive = directory / "export.tar"
    write_training_export(export, directory / "package", archive)
    return directory / "package"


@pytest.mark.parametrize("format_name", ["coco", "yolo", "imagefolder"])
def test_training_export_same_source_is_byte_identical_and_manifest_pins_version(
    export: TrainingExport, tmp_path: Path, format_name: TrainingFormat
) -> None:
    """Host paths, source ordering, directory mtimes and destination names never affect bytes."""
    selected = export.model_copy(update={"format": format_name})
    package = _write(selected, tmp_path / "first")
    _write(
        selected.model_copy(update={"items": tuple(reversed(selected.items))}), tmp_path / "second"
    )
    assert (tmp_path / "first/export.tar").read_bytes() == (
        tmp_path / "second/export.tar"
    ).read_bytes()
    manifest = json.loads((package / "MANIFEST.json").read_text())
    assert (
        manifest["source_version"],
        manifest["split_set_id"],
        manifest["seed"],
        manifest["format_version"],
    ) == ("version", "split", 42, "1.0")
    assert manifest["file_count"] == 3
    assert manifest["split_counts"] == {"train": 1, "val": 1, "test": 1}
    with tarfile.open(tmp_path / "first/export.tar") as archive:
        assert all(member.mtime == 0 and member.uid == 0 and member.gid == 0 for member in archive)
        assert all(
            not Path(member.name).is_absolute() and ".." not in Path(member.name).parts
            for member in archive
        )


def test_coco_standard_documents_roundtrip_absolute_boxes_and_empty_images(
    export: TrainingExport, tmp_path: Path
) -> None:
    """COCO documents retain categories, xywh geometry, correct area and source identities."""
    package = _write(export, tmp_path / "coco")
    records: dict[str, AnnotationRecord] = {}
    for path in (package / "annotations").glob("*.json"):
        document = CocoDataset.model_validate_json(path.read_bytes())
        records.update((record.sample_id, record) for record in import_coco(document, "reviewer"))
        for box in document.annotations:
            assert box.bbox == (10, 20, 30, 40)
            assert box.area == 1200
            assert box.iscrowd == 0
    for item in export.items:
        assert records[item.file.id].boxes == item.annotation.boxes
        assert (package / "images" / item.split / filename(item)).is_file()


def test_yolo_layout_and_normalized_boxes_roundtrip(export: TrainingExport, tmp_path: Path) -> None:
    """Each source image has a matching TXT label and data.yaml declares actual split trees."""
    package = _write(export.model_copy(update={"format": "yolo"}), tmp_path / "yolo")
    config = yaml.safe_load((package / "data.yaml").read_text())
    assert config["names"] == {0: "cat/rare"}
    assert config["train"] == "images/train"
    assert config["val"] == "images/val"
    assert config["test"] == "images/test"
    document = YoloDataset(
        names=("cat/rare",),
        images=tuple(
            YoloImage(
                sample_id=item.file.id,
                width=100,
                height=80,
                labels=(
                    package / "labels" / item.split / Path(filename(item)).with_suffix(".txt")
                ).read_text(),
            )
            for item in export.items
        ),
    )
    restored = import_yolo(document, "reviewer")
    for original, record in zip(export.items, restored, strict=True):
        assert record.boxes == original.annotation.boxes
        assert (package / "images" / original.split / filename(original)).is_file()


def test_imagefolder_escapes_category_paths(export: TrainingExport, tmp_path: Path) -> None:
    """Classification directory names cannot escape the root."""
    package = _write(export.model_copy(update={"format": "imagefolder"}), tmp_path / "imagefolder")
    assert (package / "train" / "cat%2Frare" / filename(export.items[0])).is_file()
    assert class_directory("..") != ".."
    assert class_directory("/") == "%2F"


def test_text_jsonl_keeps_unicode_and_half_open_character_offsets(tmp_path: Path) -> None:
    """Unicode character offsets remain independent of UTF-8 byte length and whitespace."""
    source = tmp_path / "text.txt"
    source.write_text("A猫\n Café!", encoding="utf-8")
    annotation = AnnotationRecord(
        sample_id="text",
        annotator_id="r",
        labels=("topic",),
        spans=(AnnotationSpan(category="animal", start=1, end=2),),
        text_length=9,
    )
    item = TrainingExportItem(
        file=_file(source, "text", "text"), split="train", annotation=annotation
    )
    export = TrainingExport(
        dataset_id="d", version_id="v", split_set_id="s", seed=1, format="text_jsonl", items=(item,)
    )
    package = _write(export, tmp_path / "text-export")
    row = json.loads((package / "train.jsonl").read_text())
    assert row["text"] == "A猫\n Café!"
    assert row["text"][row["spans"][0]["start"] : row["spans"][0]["end"]] == "猫"
    _write(export, tmp_path / "text-again")
    assert (tmp_path / "text-export/export.tar").read_bytes() == (
        tmp_path / "text-again/export.tar"
    ).read_bytes()


def test_export_refuses_changed_bytes_and_invalid_detection_geometry(
    export: TrainingExport, tmp_path: Path
) -> None:
    """Never silently package changed data or clamp invalid training boxes."""
    source = Path(export.items[0].file.path)
    source.write_bytes(b"changed")
    with pytest.raises(ConflictError, match="frozen version"):
        _write(export, tmp_path / "changed")
    item = export.items[1]
    bad = item.model_copy(
        update={
            "annotation": item.annotation.model_copy(
                update={"boxes": (AnnotationBox(category="cat", x1=-1, y1=0, x2=40, y2=60),)}
            )
        }
    )
    with pytest.raises(ValidationError, match="inside image"):
        _write(export.model_copy(update={"items": (bad,)}), tmp_path / "bad-box")


@pytest.mark.parametrize("labels", [None, (), ("one", "two")])
def test_imagefolder_refuses_ambiguous_classification(
    export: TrainingExport, tmp_path: Path, labels: tuple[str, ...] | None
) -> None:
    """A classification package must not invent a class or duplicate a multilabel sample."""
    item = export.items[0]
    item = item.model_copy(
        update={"annotation": item.annotation.model_copy(update={"labels": labels})}
    )
    with pytest.raises(ValidationError, match="exactly one"):
        _write(
            export.model_copy(update={"format": "imagefolder", "items": (item,)}), tmp_path / "bad"
        )


def test_gzip_training_archive_has_no_filename_or_timestamp_and_reproduces(
    export: TrainingExport, tmp_path: Path
) -> None:
    """Gzip framing is deterministic even when destinations have unrelated basenames."""
    first, second = tmp_path / "one.tar.gz", tmp_path / "other.tgz"
    write_training_export(export, tmp_path / "first", first)
    write_training_export(export, tmp_path / "second", second)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes()[:3] == b"\x1f\x8b\x08"
    assert first.read_bytes()[3] & 0x08 == 0
    assert first.read_bytes()[4:8] == b"\x00\x00\x00\x00"
    with tarfile.open(first) as archive:
        assert "MANIFEST.json" in archive.getnames()


def test_text_jsonl_preserves_crlf_and_carriage_return_character_positions(tmp_path: Path) -> None:
    """Reading text must never normalize newlines before interpreting source character offsets."""
    text = "A\r\n猫 B\rC"
    source = tmp_path / "windows-text.txt"
    source.write_bytes(text.encode("utf-8"))
    annotation = AnnotationRecord(
        sample_id="text",
        annotator_id="r",
        labels=("topic",),
        text_length=len(text),
        spans=(AnnotationSpan(category="animal", start=3, end=4),),
    )
    item = TrainingExportItem(
        file=_file(source, "text", "text"), split="train", annotation=annotation
    )
    export = TrainingExport(
        dataset_id="d", version_id="v", split_set_id="s", seed=1, format="text_jsonl", items=(item,)
    )
    try:
        package = _write(export, tmp_path / "crlf-export")
    except ValidationError as error:
        message = "Valid CRLF source text and character offsets must export successfully"
        raise AssertionError(message) from error
    row = json.loads((package / "train.jsonl").read_bytes())
    assert row["text"] == text
    assert row["text"][3:4] == "猫"


@pytest.mark.parametrize("format_name", ["coco", "yolo"])
def test_fractional_detection_touching_image_boundary_roundtrips(
    export: TrainingExport, tmp_path: Path, format_name: TrainingFormat
) -> None:
    """Normalized floating geometry may exceed the right edge by one ULP after restoration."""
    source = tmp_path / "fractional.png"
    Image.new("RGB", (2970, 80), (40, 90, 130)).save(source)
    original = AnnotationBox(category="cat", x1=2458.086004983466, y1=2.123456789, x2=2970, y2=80)
    annotation = AnnotationRecord(
        sample_id="fractional",
        annotator_id="r",
        boxes=(original,),
        image_width=2970,
        image_height=80,
    )
    item = TrainingExportItem(
        file=_file(source, "fractional", "image"), split="train", annotation=annotation
    )
    package = _write(
        export.model_copy(update={"format": format_name, "items": (item,)}), tmp_path / format_name
    )
    if format_name == "coco":
        records = import_coco(
            CocoDataset.model_validate_json(
                (package / "annotations/instances_train.json").read_bytes()
            ),
            "r",
        )
    else:
        labels = (package / "labels/train" / Path(filename(item)).with_suffix(".txt")).read_text()
        records = import_yolo(
            YoloDataset(
                names=("cat",),
                images=(YoloImage(sample_id="fractional", width=2970, height=80, labels=labels),),
            ),
            "r",
        )
    assert records[0].boxes is not None
    restored = records[0].boxes[0]
    assert restored.category == original.category
    assert (restored.x1, restored.y1, restored.x2, restored.y2) == pytest.approx(
        (original.x1, original.y1, original.x2, original.y2)
    )
    assert restored.x2 == 2970
    assert restored.y2 == 80


@pytest.mark.parametrize("format_name", ["coco", "yolo"])
def test_detection_export_rejects_missing_boxes_instead_of_inventing_negative(
    export: TrainingExport, tmp_path: Path, format_name: TrainingFormat
) -> None:
    """An unannotated image is different from an explicit reviewed-empty detection image."""
    item = export.items[0]
    missing = item.model_copy(
        update={"annotation": item.annotation.model_copy(update={"boxes": None})}
    )
    with pytest.raises(ValidationError, match="missing annotations are not negatives"):
        _write(
            export.model_copy(update={"format": format_name, "items": (missing,)}),
            tmp_path / format_name,
        )


def test_yolo_export_requires_explicit_category_while_empty_coco_remains_valid(
    export: TrainingExport, tmp_path: Path
) -> None:
    """Zero-category COCO is an interchange document; zero-category YOLO cannot be trained."""
    item = export.items[0]
    empty = item.model_copy(
        update={"annotation": item.annotation.model_copy(update={"boxes": (), "labels": ()})}
    )
    selected = export.model_copy(update={"items": (empty,)})
    with pytest.raises(ValidationError, match="at least one explicit detection category"):
        _write(selected.model_copy(update={"format": "yolo"}), tmp_path / "yolo-empty")
    package = _write(selected.model_copy(update={"format": "coco"}), tmp_path / "coco-empty")
    document = CocoDataset.model_validate_json(
        (package / "annotations/instances_train.json").read_bytes()
    )
    assert document.categories == ()
    assert document.annotations == ()
    assert len(document.images) == 1
    assert import_coco(document, "r")[0].boxes == ()


def test_imagefolder_classification_keeps_missing_detection_annotation_available(
    export: TrainingExport, tmp_path: Path
) -> None:
    """Classification does not require a detection review for every image."""
    item = export.items[0]
    classification = item.model_copy(
        update={"annotation": item.annotation.model_copy(update={"boxes": None})}
    )
    package = _write(
        export.model_copy(update={"format": "imagefolder", "items": (classification,)}),
        tmp_path / "classification",
    )
    assert (package / "train/cat%2Frare" / filename(classification)).is_file()
    assert json.loads((package / "classes.json").read_bytes()) == {"cat%2Frare": "cat/rare"}


def test_removed_hf_training_format_is_rejected(export: TrainingExport) -> None:
    """Both controlled-action and training boundaries reject the deferred format."""
    with pytest.raises(SchemaValidationError, match="format"):
        ExportParams.model_validate({"dataset_id": "dataset", "format": "hf_imagefolder"})
    with pytest.raises(SchemaValidationError, match="format"):
        TrainingExport.model_validate({**export.model_dump(), "format": "hf_imagefolder"})
