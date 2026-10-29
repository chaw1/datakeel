# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write standard COCO and Ultralytics YOLO detection layouts."""

from pathlib import Path

import yaml

from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import (
    CocoBox,
    CocoCategory,
    CocoDataset,
    CocoImage,
    TrainingExport,
    TrainingExportItem,
)
from datakeel.training.export_common import (
    copy_source,
    dimensions,
    filename,
    json_text,
    validate_image_extension,
    validate_orientation,
)


def detection_categories(items: tuple[TrainingExportItem, ...]) -> tuple[str, ...]:
    """Assign stable category identities from sorted explicit detection names."""
    return tuple(sorted({box.category for item in items for box in item.annotation.boxes or ()}))


def validate_detection_annotations(export: TrainingExport) -> None:
    """Require reviewed detections and at least one explicit category for YOLO training."""
    if export.format not in {"coco", "yolo"}:
        return
    if any(item.annotation.boxes is None for item in export.items):
        message = "Detection exports require reviewed boxes; missing annotations are not negatives"
        raise ValidationError(message)
    categories = detection_categories(export.items)
    if export.format == "yolo" and not categories:
        message = "YOLO exports require at least one explicit detection category"
        raise ValidationError(message)


def write_coco(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Write per-split COCO documents with absolute xywh boxes and integer identities."""
    categories = detection_categories(export.items)
    paths: dict[str, str] = {}
    for split in sorted({item.split for item in export.items}):
        selected = tuple(item for item in export.items if item.split == split)
        images: list[CocoImage] = []
        annotations: list[CocoBox] = []
        for ordinal, item in enumerate(selected, 1):
            validate_orientation(item)
            width, height = dimensions(item)
            relative = f"images/{split}/{filename(item)}"
            paths[item.file.id] = relative
            copy_source(item, directory / relative)
            images.append(
                CocoImage(
                    id=ordinal,
                    file_name=relative,
                    width=width,
                    height=height,
                    datakeel_sample_id=item.file.id,
                )
            )
            for box in item.annotation.boxes or ():
                bbox = (box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1)
                annotations.append(
                    CocoBox(
                        id=len(annotations) + 1,
                        image_id=ordinal,
                        category_id=categories.index(box.category) + 1,
                        bbox=bbox,
                        area=bbox[2] * bbox[3],
                        iscrowd=0,
                    )
                )
        document = CocoDataset(
            images=tuple(images),
            annotations=tuple(annotations),
            categories=tuple(CocoCategory(id=i, name=name) for i, name in enumerate(categories, 1)),
        )
        target = directory / "annotations" / f"instances_{split}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json_text(document.model_dump(mode="json")), encoding="utf-8", newline="\n"
        )
    return paths


def write_yolo(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Write matching images/labels trees and a relative data.yaml with zero-indexed classes."""
    categories = detection_categories(export.items)
    paths: dict[str, str] = {}
    for split in ("train", "val", "test"):
        (directory / "images" / split).mkdir(parents=True, exist_ok=True)
        (directory / "labels" / split).mkdir(parents=True, exist_ok=True)
    for item in export.items:
        validate_image_extension(item, "yolo")
        validate_orientation(item)
        width, height = dimensions(item)
        name = filename(item)
        relative = f"images/{item.split}/{name}"
        paths[item.file.id] = relative
        copy_source(item, directory / relative)
        target = directory / "labels" / item.split / Path(name).with_suffix(".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        rows: list[str] = []
        for box in item.annotation.boxes or ():
            coordinates = (
                (box.x1 + box.x2) / (2 * width),
                (box.y1 + box.y2) / (2 * height),
                (box.x2 - box.x1) / width,
                (box.y2 - box.y1) / height,
            )
            rows.append(
                " ".join(
                    [str(categories.index(box.category)), *(format(v, ".17g") for v in coordinates)]
                )
            )
        target.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8", newline="\n")
    configuration: dict[str, object] = {
        **{split: f"images/{split}" for split in ("train", "val", "test")},
        "names": dict(enumerate(categories)),
    }
    (directory / "data.yaml").write_text(
        yaml.safe_dump(configuration, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    return paths
