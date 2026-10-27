# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate segment-level temporal hashes and optional duplicate filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.operators.video.dedup import OPERATOR
from datakeel.operators.video.normalize import OPERATOR as NORMALIZE

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.video.conftest import VideoFactory


def test_dedup_repeated_window_detected_inside_recording(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A repeated temporal sequence is located even within one source file."""
    source = make_video(
        "testsrc2=size=160x96:rate=10:duration=2,split[a][b];[a][b]concat=n=2:v=1:a=0"
    )
    result = OPERATOR.run([source], output_dir)
    duplicates = result.files[0].metadata["video_metrics"]["duplicate_segments"]
    assert [(item["start_ms"], item["end_ms"], item["source_start_ms"]) for item in duplicates] == [
        (2000, 4000, 0)
    ]
    assert result.quality["duplicate_segment_count"] == 1
    filtered = OPERATOR.run([source], output_dir, {"remove": True})
    assert len(filtered.files) == 1
    assert filtered.files[0].metadata["end_ms"] == 2000


def test_dedup_matching_sequence_removed_across_files(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Different file identities with the same decoded signal share one representative."""
    first = make_video()
    second = make_video()
    result = OPERATOR.run([first, second], output_dir, {"remove": True})
    assert [file.id for file in result.files] == [first.id]


def test_dedup_distinct_luminance_and_motion_are_not_duplicates(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Uniform dHash collisions are rejected by luminance, and motion order matters."""
    dark = make_video("color=black:size=160x96:rate=10:duration=2")
    bright = make_video("color=white:size=160x96:rate=10:duration=2")
    motion = make_video()
    reverse = make_video("testsrc2=size=160x96:rate=10:duration=2,reverse")
    result = OPERATOR.run([dark, bright, motion, reverse], output_dir)
    assert result.quality["duplicate_segment_count"] == 0


def test_dedup_same_layout_with_different_motion_keeps_every_window(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A stable camera layout cannot make distinct moving sequences near-duplicates."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=12")
    result = OPERATOR.run([source], output_dir, {"window_ms": 1000})
    assert result.quality["duplicate_segment_count"] == 0


def test_dedup_reencoded_signal_is_still_near_duplicate(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """The spatial check tolerates ordinary lossy encoding differences."""
    source = make_video()
    reencoded = NORMALIZE.run(
        [source], output_dir, {"width": 160, "height": 96, "frame_rate": 10.0}
    ).files[0]
    result = OPERATOR.run([source, reencoded], output_dir)
    assert result.quality["duplicate_segment_count"] == 1


def test_dedup_distinct_colors_with_equal_luminance_are_not_duplicates(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Equal dHashes and gray texture cannot hide different chromatic source content."""
    warm = make_video("color=c=0xdf5b46:size=160x96:rate=10:duration=2")
    cool = make_video("color=c=0x21a5ba:size=160x96:rate=10:duration=2")
    result = OPERATOR.run([warm, cool], output_dir)
    assert result.quality["duplicate_segment_count"] == 0


def test_dedup_repeat_between_window_boundaries_is_located_exactly(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A repeat that starts off the window grid is found and extended to its true extent."""
    source = make_video(
        "testsrc2=size=160x96:rate=10:duration=4.7[a];"
        "testsrc2=size=160x96:rate=10:duration=4,trim=start=1.3:end=3.8,setpts=PTS-STARTPTS[b];"
        "[a][b]concat=n=2:v=1:a=0"
    )
    result = OPERATOR.run([source], output_dir, {"window_ms": 1000})
    duplicates = result.files[0].metadata["video_metrics"]["duplicate_segments"]
    assert [
        (item["start_ms"], item["end_ms"], item["source_start_ms"], item["source_end_ms"])
        for item in duplicates
    ] == [(4700, 7200, 1300, 3800)]


def test_dedup_shifted_copy_in_another_file_keeps_its_unique_lead(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A copy that starts later keeps only its unique lead-in when duplicates are removed."""
    original = make_video("testsrc2=size=160x96:rate=10:duration=3")
    shifted = make_video(
        "color=0x406080:size=160x96:rate=10:duration=0.6[a];"
        "testsrc2=size=160x96:rate=10:duration=3[b];[a][b]concat=n=2:v=1:a=0"
    )
    result = OPERATOR.run([original, shifted], output_dir, {"window_ms": 1000, "remove": True})
    kept = [file for file in result.files if file.id != original.id]
    assert [(file.metadata["start_ms"], file.metadata["end_ms"]) for file in kept] == [(0, 600)]
    assert kept[0].metadata["source_asset_id"] == shifted.id
