# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write Hugging Face imagefolder with consistent, lossless metadata across all splits."""

from pathlib import Path

from PIL import Image

from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import (
    HfImageMetadata,
    TrainingExport,
    TrainingExportItem,
)
from datakeel.training.export_common import (
    copy_source,
    dimensions,
    filename,
    json_text,
    validate_image_extension,
)

_README = """# Hugging Face imagefolder

Each nonempty split contains images and one metadata.jsonl with a row per image.
file_name is relative to its metadata file. Image bytes are unchanged.
Only absent or identity (1) EXIF orientation is accepted. Normalize rotated or
mirrored sources before importing; the HF decoder otherwise changes their frame.

Load with datasets.load_dataset("imagefolder", data_dir="package"). The loader
recognizes the val directory as the validation split. No datasets dependency is
needed to create this package.

labels_json and boxes_json are JSON text columns. Decode them with json.loads.
labels_json preserves original category strings and label order. boxes_json
preserves category, x1, y1, x2, y2 in absolute source-image pixel coordinates.
null means unreviewed; [] means reviewed empty. Other metadata columns are
sample_id, annotator_id, width and height. These scalar columns keep the same
inferred schema when a split contains only empty or missing annotations.
No synthetic examples or annotation values are inserted to influence inference.

MANIFEST.json records original split names, source hashes, counts and identities.
"""


def _validate_orientation(item: TrainingExportItem) -> None:
    with Image.open(item.file.path) as image:
        if image.getexif().get(274) not in (None, 1):
            message = (
                "HF imagefolder requires absent or identity EXIF orientation; "
                "normalize the source orientation before importing"
            )
            raise ValidationError(message)


def write_hf_imagefolder(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Write safe relative image links and nullable annotations as stable JSON text columns."""
    paths: dict[str, str] = {}
    for split in sorted({item.split for item in export.items}):
        rows: list[str] = []
        for item in (item for item in export.items if item.split == split):
            validate_image_extension(item, "hf_imagefolder")
            _validate_orientation(item)
            width, height = dimensions(item)
            name = filename(item)
            relative = f"{split}/{name}"
            copy_source(item, directory / relative)
            paths[item.file.id] = relative
            boxes = item.annotation.boxes
            row = HfImageMetadata(
                file_name=name,
                sample_id=item.file.id,
                annotator_id=item.annotation.annotator_id,
                width=width,
                height=height,
                labels_json=json_text(item.annotation.labels),
                boxes_json=json_text(
                    None if boxes is None else [box.model_dump(mode="json") for box in boxes]
                ),
            )
            rows.append(json_text(row.model_dump(mode="json")))
        (directory / split / "metadata.jsonl").write_text(
            "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
        )
    (directory / "README.md").write_text(_README, encoding="utf-8", newline="\n")
    return paths
