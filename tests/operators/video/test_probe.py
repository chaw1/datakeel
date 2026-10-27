# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify probe metadata from generated audio/video streams."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.core.errors import ValidationError as MediaValidationError
from datakeel.operators.video import OPERATORS
from datakeel.operators.video.probe import OPERATOR

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.video.conftest import VideoFactory


def test_probe_generated_av_streams_have_expected_properties(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Read actual container properties, preserving the source identity."""
    source = make_video(audio=True)
    result = OPERATOR.run([source], output_dir)
    probe = result.files[0].metadata["media_probe"]
    assert result.files[0].id == source.id
    assert probe["duration_ms"] == 2000
    assert (probe["width"], probe["height"], probe["frame_rate"]) == (160, 96, 10)
    assert (probe["codec"], probe["rotation"], probe["audio_tracks"]) == ("mpeg4", 0, 1)
    assert {operator.manifest.id for operator in OPERATORS} == {
        "video.probe",
        "video.invalid_frames",
        "video.dedup",
        "video.segment",
        "video.normalize",
    }


def test_probe_undeclared_parameters_rejected(make_video: VideoFactory, output_dir: Path) -> None:
    """Reject configuration errors before invoking an external decoder."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        OPERATOR.run([make_video()], output_dir, {"unrecognized": True})


def test_probe_audio_disguised_as_video_is_rejected(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A modality label cannot make an audio-only stream satisfy video probing."""
    source = make_video("sine=frequency=400:sample_rate=16000:duration=1")
    with pytest.raises(MediaValidationError, match="no video stream"):
        OPERATOR.run([source], output_dir)
