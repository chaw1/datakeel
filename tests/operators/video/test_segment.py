# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify real slicing, source intervals and replay-stable artifact identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.operators.video.segment import OPERATOR

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.video.conftest import VideoFactory


def test_segment_real_windows_are_decodable_and_deterministic(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Re-running an identical slice yields identical content and attribution."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=2.5", audio=True)
    first = OPERATOR.run([source], output_dir, {"window_ms": 1000})
    second = OPERATOR.run([source], output_dir, {"window_ms": 1000})
    assert [file.id for file in first.files] == [file.id for file in second.files]
    assert [(file.metadata["start_ms"], file.metadata["end_ms"]) for file in first.files] == [
        (0, 1000),
        (1000, 2000),
        (2000, 2500),
    ]
    assert all(file.metadata["media_probe"]["audio_tracks"] == 1 for file in first.files)
    assert all(
        abs(
            file.metadata["media_probe"]["duration_ms"]
            - (file.metadata["end_ms"] - file.metadata["start_ms"])
        )
        <= 150
        for file in first.files
    )
    for file in first.files:
        step = file.metadata["media_history"][-1]
        assert (file.metadata["source_asset_id"], step["source_file_id"]) == (source.id, source.id)
        assert (step["operator"], step["version"], len(step["parameters_digest"])) == (
            "video.segment",
            "1.0.0",
            64,
        )


def test_segment_short_remainder_respects_minimum(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A configured minimum can remove a shorter final remainder."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=2.2")
    result = OPERATOR.run([source], output_dir, {"window_ms": 1000, "minimum_duration_ms": 500})
    assert len(result.files) == 2


def test_segment_nonintegral_window_uses_actual_frame_boundaries(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Requested windows quantize to decoded frame boundaries without overlap."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=1.2")
    result = OPERATOR.run([source], output_dir, {"window_ms": 333})
    assert [(file.metadata["start_ms"], file.metadata["end_ms"]) for file in result.files] == [
        (0, 300),
        (300, 600),
        (600, 900),
        (900, 1200),
    ]


def test_segment_fractional_frame_rate_keeps_each_decoded_frame_once(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Millisecond attribution must not drop frames at fractional-rate boundaries."""
    source = make_video("testsrc2=size=160x96:rate=30000/1001:duration=1")
    result = OPERATOR.run([source], output_dir, {"window_ms": 333})
    assert [(file.metadata["start_ms"], file.metadata["end_ms"]) for file in result.files] == [
        (0, 334),
        (334, 667),
        (667, 1001),
    ]
    assert all(
        round(
            file.metadata["media_probe"]["duration_ms"]
            * file.metadata["media_probe"]["frame_rate"]
            / 1000
        )
        == 10
        for file in result.files
    )


def test_segment_skip_issues_cuts_only_clean_ranges(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Annotated invalid and duplicate intervals are left out of the produced clips."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=5")
    marked = source.model_copy(
        update={
            "metadata": {
                "media_issues": [
                    {"code": "black_frame", "start_ms": 0, "end_ms": 700},
                    {"code": "video_duplicate", "start_ms": 2000, "end_ms": 3300},
                ]
            }
        }
    )
    result = OPERATOR.run([marked], output_dir, {"window_ms": 1000, "skip_issues": True})
    assert [(file.metadata["start_ms"], file.metadata["end_ms"]) for file in result.files] == [
        (700, 1700),
        (1700, 2000),
        (3300, 4300),
        (4300, 5000),
    ]
