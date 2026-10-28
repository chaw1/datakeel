# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the media chain on caller-supplied local recordings from one command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.cli import parser
from datakeel.cli.media_demo import run_demo
from datakeel.core.media_models import MediaSummary
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_demo_media_source_option_is_repeatable(tmp_path: Path) -> None:
    """Every ``--source`` path is kept in order for the import."""
    first, second = tmp_path / "a.mp4", tmp_path / "b.wav"
    args = parser().parse_args(["demo-media", "--source", str(first), "--source", str(second)])
    assert args.source == [first, second]


def test_demo_media_processes_given_recordings(db: Database, tmp_path: Path) -> None:
    """Own recordings are measured, cleaned and aligned like the generated example."""
    camera, microphone = tmp_path / "camera.mkv", tmp_path / "microphone.wav"
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            (
                "color=c=black:s=96x64:r=10:d=1[b];testsrc2=s=96x64:r=10:d=3[m];"
                "[b][m]concat=n=2:v=1:a=0"
            ),
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:sample_rate=16000:duration=4:amplitude=0.3:seed=44",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(camera),
        ]
    )
    run_tool(["ffmpeg", "-y", "-i", str(camera), "-vn", "-af", "adelay=300:all=1", str(microphone)])
    result = run_demo(db, [camera, microphone])
    summary = MediaSummary.model_validate(result["quality"]["media"])
    assert summary.original_duration_ms > 0
    assert summary.clip_count > 0
    assert "black_frame" in summary.issue_distribution
    offsets = [
        file["media"]["alignment"]["offset_ms"]
        for file in result["files"]
        if file["filename"] == "microphone.wav" and file["media"]["source_file_id"] is None
    ]
    assert offsets == [300.0]


def test_demo_media_reports_partial_completion_for_unreadable_recording(
    db: Database, tmp_path: Path
) -> None:
    """One unreadable recording is listed as failed; the others are still processed."""
    camera, broken = tmp_path / "camera.mkv", tmp_path / "broken.mp4"
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=96x64:r=10:d=3",
            "-c:v",
            "ffv1",
            str(camera),
        ]
    )
    broken.write_bytes(b"not a recording" * 64)
    result = run_demo(db, [camera, broken])
    assert result["state"] == "COMPLETED"
    assert result["partial"] is True
    failed = result["failed_files"]
    assert [item["filename"] for item in failed] == ["broken.mp4"]
    assert failed[0]["operator"] == "media.align"
    summary = MediaSummary.model_validate(result["quality"]["media"])
    assert summary.partial
    assert [item.filename for item in summary.failures] == ["broken.mp4"]
    assert [score.filename for score in summary.files if score.duration_ms] != []
    assert all(score.filename != "broken.mp4" for score in summary.files)
    chapters = {chapter["title"]: chapter["body"] for chapter in result["report"]["chapters"]}
    body = chapters["音视频 / Audio and video"]
    assert "部分完成" in body
    assert "broken.mp4 (media.align)" in body
