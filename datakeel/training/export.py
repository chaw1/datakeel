# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate reproducible training archives with explicit source and annotation counts."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import JsonValue

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.training_export_models import TrainingExport, TrainingExportItem
from datakeel.training.export_common import json_text, source_geometry, write_archive
from datakeel.training.export_detection import (
    validate_detection_annotations,
    write_coco,
    write_yolo,
)
from datakeel.training.export_hf import write_hf_imagefolder
from datakeel.training.export_records import write_imagefolder, write_text_jsonl
from datakeel.training.native import write_annotations_jsonl

FORMAT_VERSION = "1.0"
_UPRIGHT_FORMATS = frozenset({"coco", "yolo", "hf_imagefolder"})
_WRITERS: dict[str, Callable[[TrainingExport, Path], dict[str, str]]] = {
    "coco": write_coco,
    "yolo": write_yolo,
    "imagefolder": write_imagefolder,
    "hf_imagefolder": write_hf_imagefolder,
    "text_jsonl": write_text_jsonl,
    "annotations_jsonl": write_annotations_jsonl,
}


def _count(item: TrainingExportItem, format_name: str) -> int:
    if format_name == "annotations_jsonl":
        return sum(
            len(value or ())
            for value in (
                item.annotation.labels,
                item.annotation.boxes,
                item.annotation.polygons,
                item.annotation.spans,
            )
        )
    if format_name in {"coco", "yolo"}:
        return len(item.annotation.boxes or ())
    if format_name == "imagefolder":
        return len(item.annotation.labels or ())
    if format_name == "hf_imagefolder":
        return len(item.annotation.labels or ()) + len(item.annotation.boxes or ())
    return len(item.annotation.labels or ()) + len(item.annotation.spans or ())


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


def _orientation(item: TrainingExportItem, format_name: str, written: Path) -> dict[str, object]:
    """Trace how an upright image export relates to its untouched original."""
    if format_name not in _UPRIGHT_FORMATS:
        return {}
    geometry = source_geometry(item)
    trace: dict[str, object] = {
        "source_orientation": geometry.orientation,
        "transform": geometry.transform,
    }
    if geometry.orientation != 1:
        with written.open("rb") as stream:
            trace["exported_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    return trace


def write_training_export(export: TrainingExport, directory: Path, archive: Path) -> None:
    """Write a format directory and byte-stable tar without destination or action timestamps."""
    validate_detection_annotations(export)
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
                **_orientation(item, export.format, directory / paths[item.file.id]),
            }
            for item in ordered.items
        ],
    }
    (directory / "MANIFEST.json").write_text(json_text(manifest), encoding="utf-8", newline="\n")
    write_archive(directory, archive)


def upright_transforms(directory: Path) -> list[JsonValue]:
    """List the files a written package re-encoded upright, for the export's lineage."""
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    return [
        {
            key: entry[key]
            for key in (
                "sample_id",
                "source_sha256",
                "source_orientation",
                "transform",
                "exported_sha256",
            )
        }
        for entry in manifest["files"]
        if entry.get("source_orientation", 1) != 1
    ]
