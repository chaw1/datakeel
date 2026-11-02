# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict integer segment boundaries and authoritative source-media validation."""

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.annotation_models import AnnotationRecord, AnnotationSegment
from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.core.production_segments import media_probe, validate_segment_media


def _record(segments: tuple[AnnotationSegment, ...] | None) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id="audio",
        annotator_id="ann",
        segments=segments,
        media_duration_ms=3250 if segments is not None else None,
    )


def _file(**changes: object) -> FileItem:
    values: dict[str, object] = {
        "id": "audio",
        "path": "audio.wav",
        "filename": "audio.wav",
        "modality": "audio",
        "metadata": {"media_probe": {"duration_ms": 3250, "codec": "pcm_s16le", "format": "wav"}},
    }
    values.update(changes)
    return FileItem.model_validate(values)


def test_half_open_segments_allow_boundaries_overlap_adjacency_and_duplicates() -> None:
    """Valid records retain exact input order without deduplication or merging."""
    segments = (
        AnnotationSegment(category="a", start_ms=0, end_ms=1),
        AnnotationSegment(category="a", start_ms=1, end_ms=1000),
        AnnotationSegment(category="b", start_ms=500, end_ms=3250),
        AnnotationSegment(category="b", start_ms=500, end_ms=3250),
    )
    record = _record(segments)
    validate_segment_media(_file(), record)
    assert record.segments == segments


@pytest.mark.parametrize("value", [True, False, 1.0, 1.5, "1", None])
def test_segment_milliseconds_require_real_integers(value: object) -> None:
    """Booleans, floats, strings and null cannot coerce into millisecond fields."""
    with pytest.raises(ModelValidationError):
        AnnotationSegment.model_validate({"category": "a", "start_ms": value, "end_ms": 2})


@pytest.mark.parametrize(("start", "end"), [(-1, 2), (0, 0), (2, 0), (2, 2), (0, 3251)])
def test_invalid_or_out_of_bounds_ranges_are_rejected(start: int, end: int) -> None:
    """Zero, reversed, negative and source-overflow intervals fail at their proper boundary."""
    if end <= start or start < 0:
        with pytest.raises(ModelValidationError):
            AnnotationSegment(category="a", start_ms=start, end_ms=end)
        return
    segment = AnnotationSegment(category="a", start_ms=start, end_ms=end)
    with pytest.raises(ValidationError, match="half-open"):
        validate_segment_media(_file(), _record((segment,)))


def test_none_and_reviewed_empty_remain_distinct_and_none_is_not_serialized() -> None:
    """Missing review state stays omitted while reviewed empty serializes as an empty array."""
    missing = _record(None)
    empty = _record(())
    assert missing.segments is None
    assert empty.segments == ()
    assert "segments" not in missing.model_dump(mode="json")
    assert "media_duration_ms" not in missing.model_dump(mode="json")
    assert empty.model_dump(mode="json")["segments"] == []


def test_segments_require_duration_at_the_model_boundary() -> None:
    """Even an empty reviewed segment array must name its source duration."""
    with pytest.raises(ModelValidationError, match="media_duration_ms"):
        AnnotationRecord(sample_id="audio", annotator_id="ann", segments=(), media_duration_ms=None)


@pytest.mark.parametrize("duration", [0, 3249, 3251])
def test_source_duration_must_match_exactly(duration: int) -> None:
    """Zero, stale and future durations cannot authorize a reviewed empty record."""
    file = _file(metadata={"media_probe": {"duration_ms": duration, "codec": "pcm_s16le"}})
    with pytest.raises(ValidationError, match=r"duration|readable"):
        validate_segment_media(file, _record(()))


def test_missing_probe_non_media_and_unsupported_codec_fail_clearly() -> None:
    """Missing prerequisites name the probe, modality or browser codec failure."""
    with pytest.raises(ValidationError, match="run the media probe"):
        media_probe(_file(metadata={}))
    with pytest.raises(ValidationError, match="audio or video"):
        media_probe(_file(modality="image"))
    with pytest.raises(ValidationError, match="does not support"):
        media_probe(
            _file(
                modality="video",
                metadata={"media_probe": {"duration_ms": 3250, "codec": "mpeg4"}},
            )
        )


def test_truncated_probe_uses_readable_not_declared_duration() -> None:
    """A truncated file permits its readable endpoint, not its declared header endpoint."""
    file = _file(
        metadata={
            "media_probe": {
                "duration_ms": 3250,
                "declared_duration_ms": 5000,
                "codec": "pcm_s16le",
            }
        }
    )
    validate_segment_media(
        file,
        _record((AnnotationSegment(category="a", start_ms=3249, end_ms=3250),)),
    )
