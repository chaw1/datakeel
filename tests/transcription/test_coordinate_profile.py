# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind declared coordinate semantics to profiles without rewriting historical recordings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.core.transcription_models import (
    CoordinateSpace,
    OCRLine,
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
    TranscriptionResult,
)
from datakeel.transcription.cache import profile_digest
from datakeel.transcription.loader import get_profile, read_recording

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput


def test_profile_when_coordinate_settings_omitted_defaults_to_legacy_pixels() -> None:
    """Legacy profile YAML needs no coordinate declaration or threshold migration."""
    profile = TranscriptionProfile(id="fixture", backend="fake", model="fixture")
    assert profile.coordinate_space == "pixel"
    assert profile.coordinate_min_median_iou == 0.3


@pytest.mark.parametrize("space", ["pixel", "normalized_1000", "normalized_1"])
def test_profile_when_coordinate_space_valid_accepts(space: CoordinateSpace) -> None:
    """Only the three declared provider coordinate conventions are supported."""
    profile = TranscriptionProfile(
        id="fixture", backend="fake", model="fixture", coordinate_space=space
    )
    assert profile.coordinate_space == space


@pytest.mark.parametrize(
    "change",
    [
        {"coordinate_space": "automatic"},
        {"coordinate_min_median_iou": -0.1},
        {"coordinate_min_median_iou": 1.1},
        {"coordinate_min_median_iou": float("nan")},
        {"coordinate_min_median_iou": float("inf")},
    ],
)
def test_profile_when_coordinate_configuration_invalid_rejects(change: dict[str, object]) -> None:
    """Reject ambiguous coordinate interpretation and unbounded comparison thresholds."""
    with pytest.raises(ValidationError):
        TranscriptionProfile.model_validate(
            {"id": "fixture", "backend": "fake", "model": "fixture", **change}
        )


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_profile_when_iou_threshold_at_boundary_accepts(threshold: float) -> None:
    """Users can disable low-IoU rejection or require exact matches explicitly."""
    profile = TranscriptionProfile(
        id="fixture", backend="fake", model="fixture", coordinate_min_median_iou=threshold
    )
    assert profile.coordinate_min_median_iou == threshold


@pytest.mark.parametrize(
    "change",
    [
        {"coordinate_space": "normalized_1000"},
        {"coordinate_space": "normalized_1"},
        {"coordinate_min_median_iou": 0.5},
    ],
)
def test_digest_when_coordinate_semantics_change_requires_new_identity(
    change: dict[str, object],
) -> None:
    """Coordinate transforms and reliability policy cannot reuse a signed cached result."""
    profile = get_profile("fake")
    assert profile_digest(profile) != profile_digest(profile.model_copy(update=change))


def test_live_examples_when_qwen_use_declared_normalized_coordinates() -> None:
    """Live Qwen profiles declare the convention while measured replay keeps old pixels."""
    for identity in (
        "bailian-qwen35-flash",
        "bailian-qwen35-flash-coordinates",
        "bailian-qwen35-flash-auto",
        "ollama-vision-local",
    ):
        assert get_profile(identity).coordinate_space == "normalized_1000"
    assert get_profile("replay-image-flash").coordinate_space == "pixel"


def test_recording_when_legacy_fields_omitted_keeps_pixel_metadata_and_geometry() -> None:
    """Historical recordings load directly without modifying their serialized bytes."""
    _, archive = read_recording(get_profile("replay-image-demo"))
    assert archive is not None
    assert archive.coordinate_space == "pixel"
    assert all(record.coordinate_space == "pixel" for record in archive.records)
    assert all(record.raw_output is None for record in archive.records)


def test_recording_when_normalized_source_keeps_materialized_lines_in_pixels(
    image_input: ImageInput,
) -> None:
    """Source metadata is distinct from the validated pixel rectangles used as evidence."""
    line = OCRLine(text="Alpha", bbox=(10, 20, 90, 40), confidence=1)
    record = TranscriptionRecord(
        text="Alpha",
        lines=(line,),
        width=image_input.width,
        height=image_input.height,
        backend="vlm",
        coordinate_space="normalized_1",
        ignored_field_count=1,
        image_hash=image_input.image_hash,
        raw_output='{"lines":[{"text":"Alpha","bbox":[0.1,0.2,0.9,0.4]}]}',
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-27",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        coordinate_space="normalized_1",
        records=(record,),
    )
    assert archive.records[0].lines == (line,)
    assert archive.records[0].coordinate_space == "normalized_1"
    assert archive.records[0].ignored_field_count == 1


def test_result_when_ignored_field_count_negative_rejects() -> None:
    """Parsing diagnostics remain a nonnegative count at the typed boundary."""
    with pytest.raises(ValidationError):
        TranscriptionResult(
            text="Alpha", width=120, height=80, backend="vlm", ignored_field_count=-1
        )
