# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep parsed visual output frozen and stricter than its provider wire envelope."""

import pytest
from pydantic import ValidationError

from datakeel.core.transcription_coordinates import LocatedTranscript


def test_located_transcript_when_extra_internal_field_present_rejects() -> None:
    """Ignoring provider annotations does not weaken the internal typed boundary."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        LocatedTranscript.model_validate({"text": "Alpha", "provider_extra": "ignored"})


def test_located_transcript_when_mutated_rejects() -> None:
    """Validated transcription output cannot be changed after crossing the boundary."""
    transcript = LocatedTranscript(text="Alpha")
    with pytest.raises(ValidationError, match="frozen_instance"):
        transcript.text = "Beta"


@pytest.mark.parametrize(
    ("space", "bbox"),
    [
        ("normalized_1000", "[100,200,900,800]"),
        ("normalized_1", "[0.1,0.2,0.9,0.8]"),
    ],
)
def test_located_transcript_when_normalized_valid_converts_to_pixels(space: str, bbox: str) -> None:
    """Both declared normalized conventions enter the same validated pixel boundary."""
    transcript = LocatedTranscript.decode(
        '{"lines":[{"text":"Alpha","bbox":' + bbox + "}]}",
        1800,
        800,
        "normalized_1000" if space == "normalized_1000" else "normalized_1",
    )
    assert transcript.text == "Alpha"
    assert transcript.lines[0].bbox == (180, 160, 1620, 640)
    assert transcript.quality_issues == ()
