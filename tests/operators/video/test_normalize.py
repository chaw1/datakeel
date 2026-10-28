# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify actual encoding, geometry and frame rate conversion."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.operators.media.tools import probe_file
from datakeel.operators.video.normalize import OPERATOR

if TYPE_CHECKING:
    from tests.operators.video.conftest import VideoFactory


def test_normalize_reencodes_geometry_fps_and_preserves_original(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Aspect ratio is retained inside the declared output canvas."""
    source = make_video(audio=True)
    before = Path(source.path).read_bytes()
    result = OPERATOR.run([source], output_dir, {"width": 128, "height": 128, "frame_rate": 15.0})
    normalized = result.files[0]
    probe = normalized.metadata["media_probe"]
    assert (probe["width"], probe["height"], probe["frame_rate"], probe["codec"]) == (
        128,
        128,
        15,
        "mpeg4",
    )
    assert probe["audio_tracks"] == 1
    assert Path(source.path).read_bytes() == before
    assert normalized.id != source.id
    assert normalized.metadata["operator"] == "video.normalize"


def test_normalize_odd_dimensions_rejected(make_video: VideoFactory, output_dir: Path) -> None:
    """Chroma-incompatible dimensions fail before decoding."""
    with pytest.raises(ValidationError, match="must be even"):
        OPERATOR.run([make_video()], output_dir, {"width": 127})


def test_normalize_rotation_is_applied_to_decoded_pixels(
    make_video: VideoFactory, output_dir: Path, tmp_path: Path
) -> None:
    """Display rotation survives probing and is consumed by actual normalization."""
    source = make_video()
    normalized = OPERATOR.run([source], output_dir, {"width": 160, "height": 96}).files[0]
    rotated_path = tmp_path / "rotated.mp4"
    content = Path(normalized.path).read_bytes()
    # The generated MP4 uses a version-zero track header: its matrix starts 44 bytes after type.
    matrix_start = content.index(b"tkhd") + 44
    matrix = struct.pack(">9i", 0, 1 << 16, 0, -(1 << 16), 0, 0, 0, 0, 1 << 30)
    rotated_path.write_bytes(content[:matrix_start] + matrix + content[matrix_start + 36 :])
    rotated = normalized.model_copy(update={"id": "rotated", "path": str(rotated_path)})
    assert abs(probe_file(rotated).rotation) == 90
    result = OPERATOR.run([rotated], output_dir, {"width": 96, "height": 160}).files[0]
    assert result.metadata["media_probe"]["rotation"] == 0
    assert (result.metadata["media_probe"]["width"], result.metadata["media_probe"]["height"]) == (
        96,
        160,
    )


def test_normalize_keeps_measured_issue_intervals_on_the_same_timeline(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Issue intervals stay valid after re-encoding because the timeline is unchanged."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=2")
    issues = [{"code": "black_frame", "start_ms": 0, "end_ms": 400, "severity": "warning"}]
    measured = source.model_copy(update={"metadata": {"media_issues": issues}})
    normalized = OPERATOR.run(
        [measured], output_dir, {"width": 64, "height": 48, "frame_rate": 15.0}
    ).files[0]
    assert normalized.id != source.id
    assert normalized.metadata["media_issues"] == issues
    assert normalized.metadata["source_end_ms"] == 2000
