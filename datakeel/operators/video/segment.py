# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cut video into exact decoded windows with source-time attribution."""

from pathlib import Path

from pydantic import Field

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, Params, summarize
from datakeel.operators.media.tools import media_artifact, probe_file
from datakeel.operators.video.frames import frame_times
from datakeel.operators.video.render import render


class SegmentParams(Params):
    """Choose fixed time windows, preserving a shorter final segment by default.

    With ``skip_issues`` the windows are laid only inside ranges free of the
    issue intervals already annotated on the file (invalid frames, duplicates).
    """

    window_ms: int = Field(default=10000, ge=100, le=3600000)
    minimum_duration_ms: int = Field(default=100, ge=1)
    skip_issues: bool = False


def _clean_ranges(file: FileItem, end_ms: float, *, skip_issues: bool) -> list[tuple[float, float]]:
    if not skip_issues:
        return [(0.0, end_ms)]
    issues = sorted(
        (issue.start_ms, issue.end_ms)
        for issue in (
            MediaInterval.model_validate(value) for value in file.metadata.get("media_issues", [])
        )
    )
    ranges: list[tuple[float, float]] = []
    cursor = 0.0
    for start_ms, stop_ms in issues:
        if start_ms > cursor:
            ranges.append((cursor, min(float(start_ms), end_ms)))
        cursor = max(cursor, float(stop_ms))
    if end_ms > cursor:
        ranges.append((cursor, end_ms))
    return [(start, stop) for start, stop in ranges if stop > start]


def _windows(
    timestamps: list[float], ranges: list[tuple[float, float]], window_frames: int, end: float
) -> list[tuple[int, int, float, float]]:
    windows: list[tuple[int, int, float, float]] = []
    for start_ms, stop_ms in ranges:
        inside = [index for index, value in enumerate(timestamps) if start_ms <= value < stop_ms]
        if not inside:
            continue
        last = inside[-1] + 1
        for frame in range(inside[0], last, window_frames):
            next_frame = min(frame + window_frames, last)
            stop = timestamps[next_frame] if next_frame < len(timestamps) else end
            windows.append((frame, next_frame, timestamps[frame], min(stop, stop_ms)))
    return windows


def execute(files: list[FileItem], output_dir: Path, params: SegmentParams) -> OperatorResult:
    """Produce independent MP4 files and record the actual frame-aligned time range."""
    output: list[FileItem] = []
    for file in files:
        probe = probe_file(file)
        fps = probe.frame_rate or 30.0
        window_frames = max(1, round(params.window_ms * fps / 1000))
        timestamps = frame_times(file)
        last_duration = timestamps[-1] - timestamps[-2] if len(timestamps) > 1 else 1000 / fps
        video_end = min(probe.duration_ms, timestamps[-1] + last_duration)
        ranges = _clean_ranges(file, video_end, skip_issues=params.skip_issues)
        for frame, next_frame, start_exact, end_exact in _windows(
            timestamps, ranges, window_frames, video_end
        ):
            start_ms, end_ms = round(start_exact), round(end_exact)
            if end_ms - start_ms < params.minimum_duration_ms:
                continue
            # Seek midway from the previous frame so rounding never drops the first frame.
            seek = (timestamps[frame - 1] + start_exact) / 2 if frame else 0.0
            content = render(file, start_ms=seek, end_ms=end_exact, frame_count=next_frame - frame)
            output.append(
                media_artifact(
                    file,
                    output_dir,
                    content,
                    "mp4",
                    "video.segment",
                    params,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
    result = summarize(files, output)
    result.quality["segment_count"] = len(output)
    return result


OPERATOR = Operator("video.segment", "video", "segmentation", SegmentParams, execute)
