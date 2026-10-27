# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Decode bounded pixel samples and assemble half-open issue intervals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from datakeel.core.errors import ValidationError
from datakeel.core.media_models import MediaInterval
from datakeel.operators.media.tools import input_path, run_tool

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.models import FileItem

FRAME_WIDTH = 160
FRAME_HEIGHT = 90


def decode_frames(file: FileItem, sample_fps: float, *, rgb: bool = False) -> NDArray[np.uint8]:
    """Decode evenly spaced grayscale or RGB frames without requiring Python codecs."""
    content = run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            input_path(file),
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={sample_fps},scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=area",
            "-pix_fmt",
            "rgb24" if rgb else "gray",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    )
    frame_size = FRAME_WIDTH * FRAME_HEIGHT * (3 if rgb else 1)
    count = len(content) // frame_size
    if count == 0 or len(content) % frame_size:
        msg = "Video contains no decodable frames"
        raise ValidationError(msg)
    shape = (count, FRAME_HEIGHT, FRAME_WIDTH, 3) if rgb else (count, FRAME_HEIGHT, FRAME_WIDTH)
    return np.frombuffer(content, dtype=np.uint8).reshape(shape)


def intervals(
    flags: list[bool], code: str, sample_fps: float, duration_ms: int, minimum_ms: int = 0
) -> list[MediaInterval]:
    """Coalesce sampled flags into bounded half-open source time intervals."""
    result: list[MediaInterval] = []
    start: int | None = None
    for index, flagged in enumerate([*flags, False]):
        if flagged and start is None:
            start = index
        elif not flagged and start is not None:
            start_ms = min(duration_ms, round(start * 1000 / sample_fps))
            end_ms = min(duration_ms, round(index * 1000 / sample_fps))
            if end_ms > start_ms and end_ms - start_ms >= minimum_ms:
                result.append(MediaInterval(code=code, start_ms=start_ms, end_ms=end_ms))
            start = None
    return result


def _laplacian(frame: NDArray[np.uint8]) -> float:
    pixels = frame.astype(np.float64)
    center = pixels[1:-1, 1:-1]
    laplacian = (
        pixels[:-2, 1:-1] + pixels[2:, 1:-1] + pixels[1:-1, :-2] + pixels[1:-1, 2:] - 4 * center
    )
    return float(np.var(laplacian))


def laplacian_variance(frames: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Measure frame detail without expanding the full recording into floating-point pixels."""
    return np.asarray([_laplacian(frames[index]) for index in range(len(frames))])


def frame_times(file: FileItem) -> list[float]:
    """Read actual decoded video presentation times in source-local milliseconds."""
    content = run_tool(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "csv=p=0",
            input_path(file),
        ]
    )
    times = [
        float(line.split(",")[0]) * 1000
        for line in content.decode().splitlines()
        if line.split(",")[0].strip()
    ]
    if not times:
        msg = "Video contains no timestamped frames"
        raise ValidationError(msg)
    return [timestamp - times[0] for timestamp in times]
