# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face metadata must load consistently without losing empty reviews or source facts."""

import hashlib
import json
import tarfile
from pathlib import Path

import pytest
from PIL import Image

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import (
    TRAINING_FORMATS,
    HfImageMetadata,
    TrainingExport,
    TrainingExportItem,
)
from datakeel.training.export import write_training_export


def _item(source: Path, record: AnnotationRecord, split: str) -> TrainingExportItem:
    content = source.read_bytes()
    return TrainingExportItem.model_validate(
        {
            "file": FileItem(
                id=record.sample_id,
                filename="../../source" + source.suffix.upper(),
                path=str(source),
                modality="image",
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
            ),
            "annotation": record,
            "split": split,
        }
    )


@pytest.fixture
def hf_export(tmp_path: Path) -> TrainingExport:
    """Freeze missing, reviewed-empty and multilingual multi-label reviews in different splits."""
    items: list[TrainingExportItem] = []
    for ordinal, split in enumerate(("train", "val", "test")):
        source = tmp_path / f"image-{ordinal}.png"
        Image.new("RGB", (47, 31), (ordinal * 30, 80, 120)).save(source)
        labels = None if ordinal == 0 else (() if ordinal == 1 else ("猫/../rare", "road\\side"))
        boxes = (
            None
            if ordinal == 0
            else (
                ()
                if ordinal == 1
                else (AnnotationBox(category="猫/../rare", x1=1.5, y1=2, x2=40, y2=29),)
            )
        )
        record = AnnotationRecord(
            sample_id=f"../identity/{ordinal}\\name",
            annotator_id="reviewer",
            labels=labels,
            boxes=boxes,
            image_width=47,
            image_height=31,
        )
        items.append(_item(source, record, split))
    return TrainingExport(
        dataset_id="dataset",
        version_id="version",
        release_id="release",
        split_set_id="split",
        seed=7,
        format="hf_imagefolder",
        items=tuple(items),
    )


def _write(export: TrainingExport, output: Path) -> Path:
    package = output / "package"
    package.mkdir(parents=True)
    write_training_export(export, package, output / "export.tar.gz")
    return package


def test_hf_metadata_preserves_original_annotations_and_empty_review_states(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """Three split-specific files carry the same scalar schema without synthetic examples."""
    package = _write(hf_export, tmp_path / "annotations")
    for item in hf_export.items:
        rows = (package / item.split / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1
        row = HfImageMetadata.model_validate_json(rows[0])
        assert row.sample_id == item.file.id
        assert row.annotator_id == item.annotation.annotator_id
        assert (row.width, row.height) == (47, 31)
        assert json.loads(row.labels_json) == (
            None if item.annotation.labels is None else list(item.annotation.labels)
        )
        assert json.loads(row.boxes_json) == (
            None
            if item.annotation.boxes is None
            else [box.model_dump(mode="json") for box in item.annotation.boxes]
        )
        assert all(isinstance(value, (str, int)) for value in row.model_dump().values())
    assert "Decode them with json.loads" in (package / "README.md").read_text(encoding="utf-8")


def test_hf_metadata_file_names_are_safe_relative_links_to_unchanged_images(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """Neither source filenames, identities nor category values can become unsafe paths."""
    package = _write(hf_export, tmp_path / "links")
    for item in hf_export.items:
        metadata = package / item.split / "metadata.jsonl"
        row = HfImageMetadata.model_validate_json(metadata.read_bytes())
        relative = Path(row.file_name)
        assert not relative.is_absolute()
        assert len(relative.parts) == 1
        assert relative.suffix == ".png"
        image_path = metadata.parent / relative
        assert image_path.is_file(), "file_name must resolve relative to metadata.jsonl"
        assert image_path.read_bytes() == Path(item.file.path).read_bytes()
    assert len(tuple(package.rglob("*.png"))) == len(hf_export.items)


def test_hf_archive_manifest_counts_labels_and_boxes_and_reproduces_bytes(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """Same version, split and format reproduce archive bytes despite item/destination ordering."""
    package = _write(hf_export, tmp_path / "first")
    _write(
        hf_export.model_copy(update={"items": tuple(reversed(hf_export.items))}),
        tmp_path / "second",
    )
    first, second = (tmp_path / name / "export.tar.gz" for name in ("first", "second"))
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads((package / "MANIFEST.json").read_bytes())
    assert manifest["format"] == "hf_imagefolder"
    assert manifest["format_version"] == "1.0"
    assert manifest["source_version"] == "version"
    assert manifest["release_id"] == "release"
    assert manifest["split_set_id"] == "split"
    assert manifest["seed"] == 7
    assert manifest["file_count"] == 3
    assert manifest["annotation_count"] == 3
    assert manifest["split_counts"] == {"train": 1, "val": 1, "test": 1}
    assert sorted(row["annotation_count"] for row in manifest["files"]) == [0, 0, 3]
    for row in manifest["files"]:
        assert (package / row["path"]).is_file()
        source = next(item.file for item in hf_export.items if item.file.id == row["sample_id"])
        assert row["source_sha256"] == source.sha256
        assert row["source_bytes"] == source.size
    with tarfile.open(first) as archive:
        assert all(member.uid == member.gid == member.mtime == 0 for member in archive)


def test_hf_format_is_available_through_both_typed_boundaries(hf_export: TrainingExport) -> None:
    """The portable writer and controlled action share the same accepted format name."""
    params = ExportParams(dataset_id="dataset", format="hf_imagefolder")
    assert params.format == hf_export.format
    assert params.format in TRAINING_FORMATS


@pytest.mark.parametrize("suffix", [".gif", ".ico", ".apng"])
def test_hf_loader_supported_extensions_keep_original_bytes(
    hf_export: TrainingExport, tmp_path: Path, suffix: str
) -> None:
    """HF permits these Pillow-readable extensions even when the other formats reject them."""
    source = tmp_path / ("supported" + suffix)
    Image.new("RGB", (32, 32), (60, 110, 90)).save(source)
    item = _item(source, AnnotationRecord(sample_id="supported", annotator_id="r"), "train")
    package = _write(hf_export.model_copy(update={"items": (item,)}), tmp_path / suffix[1:])
    row = HfImageMetadata.model_validate_json((package / "train/metadata.jsonl").read_bytes())
    assert row.file_name.endswith(suffix)
    assert (package / "train" / row.file_name).read_bytes() == source.read_bytes()


def test_hf_loader_unsupported_extension_is_explicitly_rejected(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """A decodable image must never be silently lost to the community loader's suffix filter."""
    original = hf_export.items[0]
    unsupported = original.model_copy(
        update={"file": original.file.model_copy(update={"filename": "source.unlisted"})}
    )
    caught: ValidationError | None = None
    try:
        _write(hf_export.model_copy(update={"items": (unsupported,)}), tmp_path / "unsupported")
    except ValidationError as error:
        caught = error
    assert caught is not None, "The writer must reject extensions that imagefolder ignores"
    assert "hf_imagefolder does not support source image extension .unlisted" in str(caught)
    assert not (tmp_path / "unsupported/export.tar.gz").exists()


def test_hf_loader_exif_rotation_and_mirroring_are_written_upright(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """HF orients decoded pixels itself, so oriented sources are written upright without a tag."""
    for orientation in (6, 2):
        source = tmp_path / f"orientation-{orientation}.jpg"
        exif = Image.Exif()
        exif[274] = orientation
        Image.new("RGB", (47, 31), (60, 110, 90)).save(source, exif=exif)
        original = source.read_bytes()
        upright = (31, 47) if orientation == 6 else (47, 31)
        annotation = AnnotationRecord(
            sample_id="oriented",
            annotator_id="r",
            image_width=upright[0],
            image_height=upright[1],
            boxes=(AnnotationBox(category="cat", x1=1, y1=2, x2=20, y2=30),),
        )
        item = _item(source, annotation, "train")
        package = _write(
            hf_export.model_copy(update={"items": (item,)}), tmp_path / f"o{orientation}"
        )
        row = HfImageMetadata.model_validate_json((package / "train/metadata.jsonl").read_bytes())
        assert (row.width, row.height) == upright
        assert row.file_name.endswith(".png")
        with Image.open(package / "train" / row.file_name) as image:
            assert image.size == upright
            assert image.getexif().get(274) is None
        assert source.read_bytes() == original


def test_hf_loader_identity_exif_preserves_dimensions_and_source_bytes(
    hf_export: TrainingExport, tmp_path: Path
) -> None:
    """Identity EXIF is safe for the default decoder and must not cause transcoding."""
    source = tmp_path / "identity.jpg"
    exif = Image.Exif()
    exif[274] = 1
    Image.new("RGB", (47, 31), (60, 110, 90)).save(source, exif=exif)
    item = _item(source, hf_export.items[2].annotation, "train")
    package = _write(hf_export.model_copy(update={"items": (item,)}), tmp_path / "identity")
    row = HfImageMetadata.model_validate_json((package / "train/metadata.jsonl").read_bytes())
    assert (row.width, row.height) == (47, 31)
    assert json.loads(row.boxes_json) == [
        box.model_dump(mode="json") for box in item.annotation.boxes or ()
    ]
    exported = package / "train" / row.file_name
    assert exported.read_bytes() == source.read_bytes()
    with Image.open(exported) as image:
        assert image.size == (47, 31)
        assert image.getexif().get(274) == 1
