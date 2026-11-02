# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authoritative local-media checks for half-open millisecond annotation segments."""

from collections.abc import Iterable

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.media_models import MediaProbe
from datakeel.core.models import FileItem

_AUDIO_CODECS = frozenset(
    {
        "aac",
        "flac",
        "mp3",
        "opus",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_alaw",
        "pcm_s16be",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_u8",
        "vorbis",
    }
)
_VIDEO_CODECS = frozenset({"av1", "h264", "vp8", "vp9"})
_AUDIO_FORMATS = frozenset({"flac", "mp3", "ogg", "wav"})
_VIDEO_FORMATS = frozenset({"matroska", "mov", "mp4", "webm", "m4a", "3gp", "3g2", "mj2"})


def require_no_segments(records: Iterable[AnnotationRecord], format_name: str) -> None:
    """Reject nonempty segments before any modality filter or partial archive write."""
    if any(record.segments for record in records):
        message = (
            f"{format_name} does not support audio/video segments; use webvtt or annotations_jsonl"
        )
        raise ValidationError(message)


def media_probe(file: FileItem) -> MediaProbe:
    """Require a positive decoded-duration probe on an audio/video source."""
    if file.modality not in {"audio", "video"}:
        message = f"Segment source {file.id} must be audio or video"
        raise ValidationError(message)
    raw = file.metadata.get("media_probe")
    if raw is None:
        message = f"Segment source {file.id} requires media_probe; run the media probe first"
        raise ValidationError(message)
    try:
        probe = MediaProbe.model_validate(raw)
    except ValueError as error:
        message = f"Segment source {file.id} has an invalid media_probe"
        raise ValidationError(message) from error
    if probe.duration_ms <= 0:
        message = f"Segment source {file.id} has no readable media duration"
        raise ValidationError(message)
    _require_browser_codec(file, probe)
    return probe


def _require_browser_codec(file: FileItem, probe: MediaProbe) -> None:
    codecs = _AUDIO_CODECS if file.modality == "audio" else _VIDEO_CODECS
    formats = _AUDIO_FORMATS if file.modality == "audio" else _VIDEO_FORMATS
    containers = {part.strip() for part in probe.format.split(",") if part.strip()}
    if probe.codec not in codecs or (containers and not containers <= formats):
        message = (
            f"Segment source {file.id} uses media codec/container {probe.codec}/{probe.format} "
            "that the browser player does not support"
        )
        raise ValidationError(message)


def validate_segment_media(file: FileItem, annotation: AnnotationRecord) -> None:
    """Validate every segment against the exact version file's readable local duration."""
    if annotation.segments is None:
        return
    probe = media_probe(file)
    if annotation.media_duration_ms != probe.duration_ms:
        message = (
            f"Annotation media_duration_ms must equal source duration {probe.duration_ms} "
            f"for {file.id}; reload the probed media"
        )
        raise ValidationError(message)
    for index, segment in enumerate(annotation.segments, start=1):
        if not 0 <= segment.start_ms < segment.end_ms <= probe.duration_ms:
            message = (
                f"Segment {index} must be a nonempty half-open interval inside "
                f"0..{probe.duration_ms}ms"
            )
            raise ValidationError(message)


def require_segment_sources(files: tuple[FileItem, ...]) -> None:
    """Check every source before creating or upgrading a segment project, including new tasks."""
    if not files:
        message = "Segment projects require at least one probed audio/video source"
        raise ValidationError(message)
    for file in files:
        media_probe(file)
