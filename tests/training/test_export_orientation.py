# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detection archives refuse EXIF frame changes and preserve identity-oriented source bytes."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import TrainingExport, TrainingExportItem, TrainingFormat
from datakeel.training.export import write_training_export


def _export(source: Path, format_name: TrainingFormat, orientation: int | None) -> TrainingExport:
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    Image.new("RGB", (47, 31), (60, 110, 90)).save(source, exif=exif)
    content = source.read_bytes()
    return TrainingExport(
        dataset_id="dataset",
        version_id="version",
        split_set_id="split",
        seed=7,
        format=format_name,
        items=(
            TrainingExportItem(
                file=FileItem(
                    id="image",
                    filename=source.name,
                    path=str(source),
                    modality="image",
                    sha256=hashlib.sha256(content).hexdigest(),
                    size=len(content),
                ),
                split="train",
                annotation=AnnotationRecord(
                    sample_id="image",
                    annotator_id="reviewer",
                    image_width=47,
                    image_height=31,
                    boxes=(AnnotationBox(category="cat", x1=2, y1=3, x2=40, y2=29),),
                ),
            ),
        ),
    )


def test_detection_formats_refuse_all_rotated_or_mirrored_exif_frames(tmp_path: Path) -> None:
    """COCO and YOLO must refuse all seven nonidentity directions before producing an archive."""
    for format_name in ("coco", "yolo"):
        for orientation in range(2, 9):
            source = tmp_path / f"source-{format_name}-{orientation}.jpg"
            export = _export(source, format_name, orientation)
            original = source.read_bytes()
            directory = tmp_path / f"package-{format_name}-{orientation}"
            archive = tmp_path / f"export-{format_name}-{orientation}.tar"
            caught: ValidationError | None = None
            try:
                write_training_export(export, directory, archive)
            except ValidationError as error:
                caught = error
            assert caught is not None, "Detection pixels and frozen boxes must use the same frame"
            assert "requires absent or identity EXIF orientation" in str(caught)
            assert not archive.exists()
            assert source.read_bytes() == original


def test_detection_formats_preserve_absent_or_identity_exif_and_source_geometry(
    tmp_path: Path,
) -> None:
    """Safe EXIF frames retain exact source bytes, raw dimensions and the original boxes."""
    for format_name in ("coco", "yolo"):
        for orientation in (None, 1):
            source = tmp_path / f"source-{format_name}-{orientation}.jpg"
            export = _export(source, format_name, orientation)
            original = source.read_bytes()
            directory = tmp_path / f"package-{format_name}-{orientation}"
            archive = tmp_path / f"export-{format_name}-{orientation}.tar"
            write_training_export(export, directory, archive)
            assert archive.is_file()
            (image_path,) = (directory / "images/train").glob("*.jpg")
            assert image_path.read_bytes() == original
            assert source.read_bytes() == original
            with Image.open(image_path) as image:
                assert image.size == (47, 31)
                assert image.getexif().get(274) == orientation
            if format_name == "coco":
                document = json.loads((directory / "annotations/instances_train.json").read_bytes())
                assert (document["images"][0]["width"], document["images"][0]["height"]) == (47, 31)
                assert document["annotations"][0]["bbox"] == [2, 3, 38, 26]
            else:
                (labels,) = (directory / "labels/train").glob("*.txt")
                fields = labels.read_text(encoding="utf-8").split()
                assert fields[0] == "0"
                assert tuple(map(float, fields[1:])) == (21 / 47, 16 / 31, 38 / 47, 26 / 31)
