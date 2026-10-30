# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upright exports: an Ultralytics-style reader finds the marked object inside every box."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageOps

from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.image_orientation import ImageGeometry, display_record
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import TrainingExport, TrainingExportItem, TrainingFormat
from datakeel.training.export import write_training_export
from datakeel.training.export_common import dimensions

STORED = (60, 40)
MARK = (8, 6, 26, 18)  # stored-frame x1, y1, x2, y2 of the red object
RED = (230, 20, 20)


def _source(path: Path, orientation: int) -> FileItem:
    image = Image.new("RGB", STORED, (20, 120, 220))
    image.paste(RED, MARK)
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, exif=exif)
    content = path.read_bytes()
    return FileItem(
        id=f"image-{orientation}",
        filename=path.name,
        path=str(path),
        modality="image",
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


def _export(tmp_path: Path, format_name: TrainingFormat) -> TrainingExport:
    items: list[TrainingExportItem] = []
    for orientation in range(1, 9):
        file = _source(tmp_path / f"o{orientation}.png", orientation)
        stored = AnnotationRecord(
            sample_id=file.id,
            annotator_id="reviewer",
            labels=("mark",),
            image_width=STORED[0],
            image_height=STORED[1],
            boxes=(AnnotationBox(category="mark", x1=8, y1=6, x2=26, y2=18),),
        )
        geometry = ImageGeometry(
            orientation=orientation, stored_width=STORED[0], stored_height=STORED[1]
        )
        items.append(
            TrainingExportItem(
                file=file, split="train", annotation=display_record(stored, geometry)
            )
        )
    return TrainingExport(
        dataset_id="dataset",
        version_id="version",
        split_set_id="split",
        seed=1,
        format=format_name,
        items=tuple(items),
    )


def _ultralytics_pixels(path: Path) -> Image.Image:
    """Read like Ultralytics: decode, then apply EXIF orientation before using any size."""
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _assert_marked(image: Image.Image, box: tuple[float, ...]) -> None:
    """The box covers exactly the red object: every pixel inside is red, none outside."""
    pixels = np.asarray(image)
    red = (pixels[..., 0] > 180) & (pixels[..., 2] < 90)
    x1, y1, x2, y2 = (round(value) for value in box)
    assert red[y1:y2, x1:x2].all(), box
    assert int(red.sum()) == (x2 - x1) * (y2 - y1), box


def _boxes(directory: Path, format_name: str) -> dict[str, tuple[Path, tuple[float, ...]]]:
    manifest = json.loads((directory / "MANIFEST.json").read_bytes())
    paths = {row["sample_id"]: directory / row["path"] for row in manifest["files"]}
    result: dict[str, tuple[Path, tuple[float, ...]]] = {}
    if format_name == "coco":
        document = json.loads((directory / "annotations/instances_train.json").read_bytes())
        for image in document["images"]:
            (box,) = (a["bbox"] for a in document["annotations"] if a["image_id"] == image["id"])
            sample = image["datakeel_sample_id"]
            with Image.open(paths[sample]) as decoded:
                assert decoded.size == (image["width"], image["height"])
            result[sample] = (paths[sample], (box[0], box[1], box[0] + box[2], box[1] + box[3]))
    elif format_name == "yolo":
        for sample, path in paths.items():
            label = directory / "labels/train" / (path.stem + ".txt")
            _, cx, cy, w, h = (float(value) for value in label.read_text().split())
            width, height = _ultralytics_pixels(path).size
            box = ((cx - w / 2) * width, (cy - h / 2) * height)
            result[sample] = (path, (*box, box[0] + w * width, box[1] + h * height))
    else:
        rows = (directory / "train/metadata.jsonl").read_text().splitlines()
        for row in map(json.loads, rows):
            (box,) = json.loads(row["boxes_json"])
            path = directory / "train" / row["file_name"]
            assert _ultralytics_pixels(path).size == (row["width"], row["height"])
            result[row["sample_id"]] = (path, (box["x1"], box["y1"], box["x2"], box["y2"]))
    return result


@pytest.mark.parametrize("format_name", ["coco", "yolo", "hf_imagefolder"])
def test_every_exif_orientation_exports_pixels_and_boxes_in_one_upright_frame(
    tmp_path: Path, format_name: TrainingFormat
) -> None:
    """All eight EXIF values, mirrors included, put each exported box on the same red object."""
    export = _export(tmp_path, format_name)
    originals = {item.file.id: Path(item.file.path).read_bytes() for item in export.items}
    directory = tmp_path / "package"
    write_training_export(export, directory, tmp_path / "export.tar")
    boxes = _boxes(directory, format_name)
    assert sorted(boxes) == sorted(originals)
    for sample, (path, box) in boxes.items():
        with Image.open(path) as image:
            assert image.getexif().get(274) in (None, 1)
        _assert_marked(_ultralytics_pixels(path), box)  # type: ignore[arg-type]
        source = Path(next(i.file.path for i in export.items if i.file.id == sample))
        assert source.read_bytes() == originals[sample]
    upright = directory / json.loads((directory / "MANIFEST.json").read_bytes())["files"][0]["path"]
    assert upright.is_file()


def test_manifest_traces_original_orientation_and_transform(tmp_path: Path) -> None:
    """Lineage names the untouched original, its EXIF value and the applied transpose."""
    export = _export(tmp_path, "yolo")
    directory = tmp_path / "package"
    write_training_export(export, directory, tmp_path / "export.tar")
    rows = {
        row["sample_id"]: row
        for row in json.loads((directory / "MANIFEST.json").read_bytes())["files"]
    }
    assert rows["image-1"]["transform"] == "none"
    assert "exported_sha256" not in rows["image-1"]
    assert (directory / rows["image-1"]["path"]).read_bytes() == Path(
        tmp_path / "o1.png"
    ).read_bytes()
    expected = {2: "flip_left_right", 3: "rotate_180", 6: "rotate_270", 8: "rotate_90"}
    for orientation, transform in expected.items():
        row = rows[f"image-{orientation}"]
        assert (row["source_orientation"], row["transform"]) == (orientation, transform)
        written = (directory / row["path"]).read_bytes()
        assert row.get("exported_sha256") == hashlib.sha256(written).hexdigest()
        assert (
            row["source_sha256"]
            == hashlib.sha256((tmp_path / f"o{orientation}.png").read_bytes()).hexdigest()
        )


def test_detection_size_is_the_upright_size_for_all_eight_values(tmp_path: Path) -> None:
    """Without recorded sizes, exported width and height still follow the upright pixels."""
    for item in _export(tmp_path, "coco").items:
        geometry = ImageGeometry(
            orientation=int(item.file.id.removeprefix("image-")),
            stored_width=STORED[0],
            stored_height=STORED[1],
        )
        corner = AnnotationBox(category="mark", x1=1, y1=1, x2=9, y2=9)
        sizeless = item.annotation.model_copy(
            update={"image_width": None, "image_height": None, "boxes": (corner,)}
        )
        upright = (STORED[1], STORED[0]) if geometry.orientation >= 5 else STORED
        assert dimensions(item.model_copy(update={"annotation": sizeless}), geometry) == upright
