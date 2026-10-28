# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Clips start at their recorded frame in containers that have no seek index.

MPEG-TS carries no keyframe index, and an input-side seek into the middle of a
group of pictures can land on the *next* keyframe: the clip then silently loses
up to a whole GOP while its lineage still claims the requested start, and when
the requested frames never arrive ffmpeg waits until the command times out.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

_RATE = 25
_FRAMES = 80
_STEP = 2.5  # luma levels per frame index


def _numbered_capture(tmp_path: Path, gop: int) -> FileItem:
    """Encode a broadcast-style TS whose frame brightness spells the frame index."""
    path = tmp_path / f"capture-g{gop}.ts"
    seconds = _FRAMES / _RATE
    run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=64x48:r={_RATE}:d={seconds},geq=lum='16+{_STEP}*N':cb=128:cr=128",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:v",
            "mpeg4",
            "-q:v",
            "1",
            "-g",
            str(gop),
            "-bf",
            "2",
            "-c:a",
            "aac",
            "-f",
            "mpegts",
            str(path),
        ]
    )
    content = path.read_bytes()
    return FileItem(
        path=str(path),
        filename=path.name,
        size=len(content),
        modality="video",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _frame_indices(path: str) -> list[int]:
    decode = ["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0", "-fps_mode", "passthrough"]
    raw = run_tool([*decode, "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"])
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 48 * 64).astype(np.float64)
    # Gray output expands limited-range luma 16..235 to 0..255.
    return [round(float(frame.mean()) * 219 / 255 / _STEP) for frame in frames]


@pytest.mark.parametrize("gop", [250, 15])
def test_ts_clips_start_at_recorded_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gop: int
) -> None:
    """Every clip holds exactly the frames its recorded source range names."""
    monkeypatch.setenv("DATAKEEL_MEDIA_TIMEOUT_BASE_SECONDS", "30")
    source = _numbered_capture(tmp_path, gop)
    assert _frame_indices(source.path) == list(range(_FRAMES))
    result = REGISTRY["video.segment"].run([source], tmp_path / "out", {"window_ms": 1000})
    assert not result.quality["failed_files"]
    frame_ms = 1000 / _RATE
    covered: list[int] = []
    for clip in result.files:
        first = round(clip.metadata["start_ms"] / frame_ms)
        last = round(clip.metadata["end_ms"] / frame_ms)
        assert _frame_indices(clip.path) == list(range(first, last))
        covered.extend(range(first, last))
    assert covered == list(range(_FRAMES))
