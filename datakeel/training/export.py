# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate reproducible training archives with explicit source and annotation counts."""

import hashlib
from collections.abc import Callable
from pathlib import Path

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.training_export_models import TrainingExport, TrainingExportItem
from datakeel.training.export_common import json_text, write_archive
from datakeel.training.export_detection import write_coco, write_yolo
from datakeel.training.export_records import (
    write_hf_imagefolder,
    write_imagefolder,
    write_text_jsonl,
)

FORMAT_VERSION = "1.0"
_WRITERS: dict[str, Callable[[TrainingExport, Path], dict[str, str]]] = {
    "coco": write_coco,
    "yolo": write_yolo,
    "imagefolder": write_imagefolder,
    "hf_imagefolder": write_hf_imagefolder,
    "text_jsonl": write_text_jsonl,
}


def _count(item: TrainingExportItem, format_name: str) -> int:
    if format_name in {"coco", "yolo"}:
        return len(item.annotation.boxes or ())
    if format_name == "imagefolder":
        return len(item.annotation.labels or ())
    geometries = item.annotation.spans if format_name == "text_jsonl" else item.annotation.boxes
    return len(item.annotation.labels or ()) + len(geometries or ())


def _verify_sources(export: TrainingExport) -> None:
    identities = [item.file.id for item in export.items]
    if not identities or len(identities) != len(set(identities)):
        message = "Training exports require nonempty, distinct source identities"
        raise ValidationError(message)
    for item in export.items:
        source = Path(item.file.path)
        with source.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if checksum != item.file.sha256 or source.stat().st_size != item.file.size:
            message = "Source content differs from the frozen version"
            raise ConflictError(message)


def write_training_export(export: TrainingExport, directory: Path, archive: Path) -> None:
    """Write a format directory and byte-stable tar without destination or action timestamps."""
    _verify_sources(export)
    ordered = export.model_copy(
        update={"items": tuple(sorted(export.items, key=lambda i: i.file.id))}
    )
    directory.mkdir(parents=True, exist_ok=True)
    paths = _WRITERS[export.format](ordered, directory)
    manifest = {
        "format": export.format,
        "format_version": FORMAT_VERSION,
        "dataset_id": export.dataset_id,
        "source_version": export.version_id,
        "release_id": export.release_id,
        "split_set_id": export.split_set_id,
        "seed": export.seed,
        "file_count": len(ordered.items),
        "annotation_count": sum(_count(item, export.format) for item in ordered.items),
        "split_counts": {
            split: sum(i.split == split for i in ordered.items)
            for split in ("train", "val", "test")
        },
        "files": [
            {
                "sample_id": item.file.id,
                "split": item.split,
                "path": paths[item.file.id],
                "source_sha256": item.file.sha256,
                "source_bytes": item.file.size,
                "annotator_id": item.annotation.annotator_id,
                "annotation_count": _count(item, export.format),
            }
            for item in ordered.items
        ],
    }
    (directory / "MANIFEST.json").write_text(json_text(manifest), encoding="utf-8", newline="\n")
    write_archive(directory, archive)
