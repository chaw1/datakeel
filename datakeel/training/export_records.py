# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write ImageFolder and character-offset text JSONL."""

from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import TrainingExport
from datakeel.training.export_common import (
    class_directory,
    copy_source,
    dimensions,
    filename,
    json_text,
    source_text,
)


def write_imagefolder(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Write exactly one class directory per image, refusing missing or multilabel classes."""
    paths: dict[str, str] = {}
    for item in export.items:
        labels = item.annotation.labels
        if labels is None or len(labels) != 1:
            message = "ImageFolder requires exactly one classification label per image"
            raise ValidationError(message)
        dimensions(item)
        relative = f"{item.split}/{class_directory(labels[0])}/{filename(item)}"
        copy_source(item, directory / relative)
        paths[item.file.id] = relative
    classes = {
        class_directory(label): label
        for item in export.items
        for label in item.annotation.labels or ()
    }
    (directory / "classes.json").write_text(json_text(classes), encoding="utf-8", newline="\n")
    return paths


def write_text_jsonl(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Write exact UTF-8 text and half-open Python character offsets without normalization."""
    paths: dict[str, str] = {}
    for split in sorted({item.split for item in export.items}):
        rows: list[str] = []
        for item in (item for item in export.items if item.split == split):
            text = source_text(item)
            spans = item.annotation.spans or ()
            if any(not 0 <= span.start < span.end <= len(text) for span in spans):
                message = (
                    "Text spans must be nonempty half-open character intervals inside the text"
                )
                raise ValidationError(message)
            if item.annotation.text_length is not None and item.annotation.text_length != len(text):
                message = "Annotation text length differs from source text"
                raise ValidationError(message)
            rows.append(
                json_text(
                    {
                        "sample_id": item.file.id,
                        "text": text,
                        "labels": item.annotation.labels,
                        "spans": [span.model_dump(mode="json") for span in spans],
                    }
                )
            )
            paths[item.file.id] = f"{split}.jsonl"
        (directory / f"{split}.jsonl").write_text(
            "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
        )
    return paths
