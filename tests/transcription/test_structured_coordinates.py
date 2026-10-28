# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Decode provider coordinate conventions without exposing unparsed wire envelopes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from datakeel.core.transcription_models import TranscriptionRecord, TranscriptionRecording
from datakeel.transcription.adapters import ReplayTranscriber
from datakeel.transcription.coordinates import decode_coordinates

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput


def test_normalized_1000_output_uses_original_image_pixels() -> None:
    """Normalized provider coordinates scale each axis by its corrected image dimension."""
    content = '{"lines":[{"text":"Alpha","bbox":[250,100,750,900]}]}'
    parsed = decode_coordinates(content, 1600, 600, "normalized_1000")
    assert parsed.text == "Alpha"
    assert len(parsed.lines) == 1
    assert parsed.lines[0].bbox == (400, 60, 1200, 540)
    assert parsed.quality_issues == ()


def test_normalized_one_output_uses_original_image_pixels() -> None:
    """Fractional source coordinates use the original width and height independently."""
    content = '{"lines":[{"text":"Alpha","bbox":[0.25,0.1,0.75,0.9]}]}'
    parsed = decode_coordinates(content, 1600, 600, "normalized_1")
    assert parsed.lines[0].bbox == (400, 60, 1200, 540)


@pytest.mark.parametrize("dimension", [2007, 2011, 4014])
def test_normalized_full_image_boundaries_do_not_overflow_due_to_float_rounding(
    dimension: int,
) -> None:
    """A full normalized rectangle remains inside original dimensions with inexact scale factors."""
    content = '{"lines":[{"text":"Alpha","bbox":[0,0,1000,1000]}]}'
    parsed = decode_coordinates(content, dimension, dimension, "normalized_1000")
    assert len(parsed.lines) == 1
    assert parsed.lines[0].bbox == (0, 0, dimension, dimension)


def test_legacy_pixel_output_retains_original_coordinates() -> None:
    """An omitted coordinate convention preserves historical pixel recordings exactly."""
    content = '{"lines":[{"text":"Alpha","bbox":[400,60,1200,540]}]}'
    assert decode_coordinates(content, 1600, 600).lines[0].bbox == (400, 60, 1200, 540)


def test_unknown_line_fields_are_counted_and_cannot_discard_readable_text() -> None:
    """Harmless provider annotations are ignored independently for each readable line."""
    content = json.dumps(
        {
            "lines": [
                {"text": "Alpha", "bbox": [1, 2, 100, 20], "color": "gray"},
                {"text": "Beta", "bbox": [1, 30, 100, 50], "weight": 2, "style": {}},
            ]
        }
    )
    parsed = decode_coordinates(content, 120, 80)
    assert parsed.text == "Alpha\nBeta"
    assert [line.text for line in parsed.lines] == ["Alpha", "Beta"]
    assert parsed.ignored_field_count == 3
    assert parsed.quality_issues == ()


@pytest.mark.parametrize(
    "bbox",
    [
        [-1, 0, 50, 50],
        [1, 1, 121, 50],
        [1, 1, 50, 81],
        [1, 1, 1, 50],
        [50, 1, 1, 50],
        [1, 50, 50, 1],
        [1, 1, True, 50],
        [1, 1, "50", 50],
        [1, 1, float("nan"), 50],
        [1, 1, float("inf"), 50],
        [1, 1, 50],
        None,
    ],
)
def test_invalid_single_line_geometry_preserves_all_text_and_other_line(bbox: object) -> None:
    """One invalid rectangle removes that location without losing either line's text."""
    content = json.dumps(
        {"lines": [{"text": "Alpha", "bbox": bbox}, {"text": "Beta", "bbox": [1, 2, 90, 20]}]}
    )
    parsed = decode_coordinates(content, 120, 80)
    assert parsed.text == "Alpha\nBeta"
    assert [(line.text, line.bbox) for line in parsed.lines] == [("Beta", (1, 2, 90, 20))]
    assert parsed.quality_issues == ()


@pytest.mark.parametrize("maximum", [1001, 1.001])
def test_normalized_rectangle_outside_declared_extent_keeps_unlocated_text(maximum: float) -> None:
    """Original image dimensions cannot make an out-of-convention source box appear valid."""
    space = "normalized_1000" if maximum > 2 else "normalized_1"
    content = json.dumps({"lines": [{"text": "Alpha", "bbox": [0, 0, maximum, maximum]}]})
    parsed = decode_coordinates(content, 1800, 880, space)
    assert parsed.text == "Alpha"
    assert parsed.lines == ()
    assert parsed.quality_issues == ()


@pytest.mark.parametrize(
    "wrapper",
    [
        "{}",
        "```json\n{}\n```",
        "Here is the transcription:\n```json\n{}\n```\nDone.",
        "Explanation before {} and after.",
        "Metadata [] precedes the transcription {}.",
        'Metadata ["note"] precedes the transcription {}.',
    ],
)
def test_structured_wrappers_are_removed_before_line_text_is_published(wrapper: str) -> None:
    """Markdown fences and harmless surrounding prose never enter the transcript body."""
    payload = '{"lines":[{"text":"Alpha","bbox":[1,2,90,20]}]}'
    parsed = decode_coordinates(wrapper.format(payload), 120, 80)
    assert parsed.text == "Alpha"
    assert parsed.lines[0].bbox == (1, 2, 90, 20)


def test_bare_line_array_and_partly_malformed_rows_keep_only_readable_lines() -> None:
    """An unsupported individual row cannot discard readable neighboring model lines."""
    content = '[null,42,{"text":7},{"bbox":[1,2,3,4]},{"text":"Alpha"},{"text":"Beta"}]'
    parsed = decode_coordinates(content, 120, 80)
    assert parsed.text == "Alpha\nBeta"
    assert parsed.lines == ()
    assert parsed.quality_issues == ()


@pytest.mark.parametrize(
    "content",
    [
        "not parseable structured output",
        '{"lines": malformed}',
        '{"text":"unexpected envelope"}',
        '{"lines":[{"text":42}]}',
        '{"lines":[]}',
        "```json\n{incomplete\n```",
    ],
)
def test_unparseable_structured_output_never_publishes_raw_json(content: str) -> None:
    """Total decoding failure carries a typed issue and an empty safe transcript body."""
    parsed = decode_coordinates(content, 120, 80)
    assert parsed.text == ""
    assert parsed.lines == ()
    assert parsed.quality_issues == ("unparseable_structured_output",)


def test_normalized_recording_replays_wrapped_annotations_and_invalid_line_geometry(
    image_input: ImageInput,
) -> None:
    """A portable raw recording reproduces scaling, tolerant rows and safe readable text."""
    raw = json.dumps(
        {
            "lines": [
                {"text": "Alpha", "bbox": [100, 200, 900, 400], "color": "gray"},
                {"text": "Beta", "bbox": [100, 200, 900, 1100]},
            ]
        }
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-27",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        coordinate_space="normalized_1000",
        records=(
            TranscriptionRecord(
                image_hash=image_input.image_hash,
                text="",
                raw_output=f"Explanation:\n```json\n{raw}\n```\nDone.",
                width=image_input.width,
                height=image_input.height,
                backend="vlm",
            ),
        ),
    )
    result = ReplayTranscriber(archive, mode="vlm").transcribe(image_input)
    assert result.text == "Alpha\nBeta"
    assert [(line.text, line.bbox) for line in result.lines] == [("Alpha", (12, 16, 108, 32))]
    assert result.coordinate_space == "normalized_1000"
    assert result.ignored_field_count == 1
    assert result.quality_issues == ()
