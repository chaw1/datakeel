# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise issue detection against independent generated pixel signals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.operators.video.invalid_frames import OPERATOR

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.video.conftest import VideoFactory


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("color=black:size=160x96:rate=10:duration=1.6", "black_frame"),
        ("color=red:size=160x96:rate=10:duration=1.6", "solid_frame"),
        (
            "testsrc2=size=160x96:rate=10:duration=1,tpad=stop_mode=clone:stop_duration=1.6",
            "frozen_frame",
        ),
        ("testsrc2=size=160x96:rate=10:duration=1.6,gblur=sigma=18", "blurred_frame"),
    ],
)
def test_invalid_frames_generated_signals_report_intervals(
    make_video: VideoFactory, output_dir: Path, expression: str, expected: str
) -> None:
    """Measure issue signals rather than matching filenames or fixture identities."""
    source = make_video(expression)
    marked = OPERATOR.run([source], output_dir).files[0]
    intervals = [issue for issue in marked.metadata["media_issues"] if issue["code"] == expected]
    assert intervals
    assert all(
        0 <= item["start_ms"] < item["end_ms"] <= marked.metadata["media_probe"]["duration_ms"]
        for item in intervals
    )
    assert 0 < marked.metadata["video_metrics"]["invalid_ratio"] <= 1


def test_invalid_frames_moving_pattern_has_no_issue(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A detailed moving pattern must avoid the dark, blur, solid and freeze flags."""
    marked = OPERATOR.run([make_video()], output_dir).files[0]
    assert marked.metadata["media_issues"] == []


def test_invalid_frames_preserves_partial_recordings_and_removes_wholly_bad(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Filtering removes a wholly bad recording while keeping its valid counterpart."""
    broken = make_video("color=black:size=160x96:rate=10:duration=1")
    valid = make_video()
    filtered = OPERATOR.run([broken, valid], output_dir, {"remove": True})
    assert [file.id for file in filtered.files] == [valid.id]
    assert filtered.quality["removed_count"] == 1


def test_invalid_frames_disjoint_black_ranges_keep_middle_valid(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Consecutive issue ranges never charge overlapping signals more than once."""
    source = make_video(
        "color=black:size=160x96:rate=10:duration=1[a];"
        "testsrc2=size=160x96:rate=10:duration=1[b];"
        "color=black:size=160x96:rate=10:duration=1[c];"
        "[a][b][c]concat=n=3:v=1:a=0"
    )
    marked = OPERATOR.run([source], output_dir, {"remove": True}).files[0]
    black = [item for item in marked.metadata["media_issues"] if item["code"] == "black_frame"]
    assert [(item["start_ms"], item["end_ms"]) for item in black] == [(0, 1000), (2000, 3000)]
    assert marked.metadata["video_metrics"]["invalid_duration_ms"] == 2000


def test_invalid_frames_motion_jump_separates_frozen_intervals(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """A sharp visual change divides two static runs instead of falsely bridging them."""
    source = make_video(
        "testsrc2=size=160x96:rate=10:duration=0.1,tpad=stop_mode=clone:stop_duration=1.4[a];"
        "testsrc2=size=160x96:rate=10:duration=3,trim=start=2.5:end=2.6,setpts=PTS-STARTPTS,"
        "tpad=stop_mode=clone:stop_duration=1.4[b];[a][b]concat=n=2:v=1:a=0"
    )
    marked = OPERATOR.run([source], output_dir).files[0]
    frozen = [item for item in marked.metadata["media_issues"] if item["code"] == "frozen_frame"]
    assert [(item["start_ms"], item["end_ms"]) for item in frozen] == [(0, 1500), (1500, 3000)]


def test_invalid_frames_brief_static_image_does_not_pass_freeze_duration(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """The configured freeze-duration threshold excludes short held pictures."""
    source = make_video(
        "testsrc2=size=160x96:rate=10:duration=0.1,tpad=stop_mode=clone:stop_duration=0.5"
    )
    marked = OPERATOR.run([source], output_dir).files[0]
    assert not any(item["code"] == "frozen_frame" for item in marked.metadata["media_issues"])


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("color=black:size=160x96:rate=10:duration=1.6", "black_frame"),
        ("color=0x3070c0:size=160x96:rate=10:duration=1.6", "solid_frame"),
    ],
)
def test_invalid_frames_uniform_picture_reports_only_its_specific_defect(
    make_video: VideoFactory, output_dir: Path, expression: str, expected: str
) -> None:
    """A black or uniform picture is not reported again as blurred or frozen."""
    marked = OPERATOR.run([make_video(expression)], output_dir).files[0]
    assert {item["code"] for item in marked.metadata["media_issues"]} == {expected}


def test_invalid_frames_blurred_content_is_not_uniform(
    make_video: VideoFactory, output_dir: Path
) -> None:
    """Heavily blurred moving content keeps the blur label and no uniform label."""
    source = make_video("testsrc2=size=160x96:rate=10:duration=1.6,boxblur=12:4")
    marked = OPERATOR.run([source], output_dir).files[0]
    assert {item["code"] for item in marked.metadata["media_issues"]} == {"blurred_frame"}
