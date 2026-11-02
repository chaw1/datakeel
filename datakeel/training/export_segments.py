# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""WebVTT-only projection and eager rejection for lossy training formats."""

from collections.abc import Iterable
from pathlib import Path

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.production_segments import validate_segment_media
from datakeel.core.training_export_models import TrainingExport, TrainingExportItem
from datakeel.training.export_common import copy_source, filename


def require_no_segments(records: Iterable[AnnotationRecord], format_name: str) -> None:
    """Reject nonempty segments before any modality filter or partial archive write."""
    if any(record.segments for record in records):
        message = (
            f"{format_name} does not support audio/video segments; use webvtt or annotations_jsonl"
        )
        raise ValidationError(message)


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def webvtt_text(item: TrainingExportItem) -> str:
    """Project one reviewed record to stable cues without claiming attribute round trips."""
    annotation = item.annotation
    if annotation.segments is None:
        message = f"WebVTT requires reviewed segments for {item.file.id}; unreviewed is not empty"
        raise ValidationError(message)
    validate_segment_media(item.file, annotation)
    lines = [
        "WEBVTT",
        "",
        f"NOTE sample_id={item.file.id} media_duration_ms={annotation.media_duration_ms}",
        "",
    ]
    ordered = sorted(
        enumerate(annotation.segments),
        key=lambda pair: (pair[1].start_ms, pair[1].end_ms, pair[0]),
    )
    for original, segment in ordered:
        lines.extend(
            (
                f"segment-{original + 1}",
                f"{_timestamp(segment.start_ms)} --> {_timestamp(segment.end_ms)}",
                segment.category,
                "",
            )
        )
    return "\n".join(lines)


def write_webvtt(export: TrainingExport, directory: Path) -> dict[str, str]:
    """Copy original media bytes and write one deterministic VTT beside each split's media."""
    paths: dict[str, str] = {}
    for item in export.items:
        media_name = filename(item)
        media_relative = f"media/{item.split}/{media_name}"
        cue_relative = f"annotations/{item.split}/{Path(media_name).with_suffix('.vtt')}"
        copy_source(item, directory / media_relative)
        cue_path = directory / cue_relative
        cue_path.parent.mkdir(parents=True, exist_ok=True)
        cue_path.write_text(webvtt_text(item), encoding="utf-8", newline="\n")
        paths[item.file.id] = media_relative
    return paths
