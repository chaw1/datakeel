# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lossless portable core annotation records for every workbench component."""

from pathlib import Path

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import TrainingExport
from datakeel.training.export_common import copy_source, filename, json_text


def write_annotations_jsonl(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Copy original sources and exact core records, retaining null, empty and attribute values."""
    paths: dict[str, str] = {}
    rows: list[str] = []
    for item in export.items:
        relative = f"sources/{item.split}/{filename(item)}"
        copy_source(item, directory / relative)
        paths[item.file.id] = relative
        rows.append(json_text(item.annotation.model_dump(mode="json")))
    (directory / "annotations.jsonl").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
    )
    return paths


def import_annotations_jsonl(content: str) -> tuple[AnnotationRecord, ...]:
    """Validate complete core records without remapping categories, geometry or attributes."""
    records = tuple(
        AnnotationRecord.model_validate_json(line) for line in content.splitlines() if line.strip()
    )
    identities = [(record.sample_id, record.annotator_id) for record in records]
    if not records or len(identities) != len(set(identities)):
        message = "Native annotation imports require nonempty, distinct sample/annotator records"
        raise ValidationError(message)
    return records
