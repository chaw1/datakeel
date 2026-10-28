# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Long recordings are processed in fixed-size blocks with whole-recording results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool
from datakeel.operators.video import analysis, sequence

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_REPLAY = (
    "testsrc2=s=160x96:r=10:d=0.1,tpad=stop_mode=clone:stop_duration=8[bg];"
    "color=c=red:s=10x16:r=10:d=8[box];"
    "[bg][box]overlay=x='5+t*15':y='30+t*3':shortest=1,split=3[a][b][c];"
    "[a]trim=0:5,setpts=PTS-STARTPTS[x];[b]trim=1:3,setpts=PTS-STARTPTS[y];"
    "[c]trim=7:8,setpts=PTS-STARTPTS[z];[x][y][z]concat=n=3:v=1:a=0"
)


def _duplicate_windows(directory: Path, file: FileItem) -> list[dict[str, object]]:
    marked = REGISTRY["video.dedup"].run([file], directory, {"window_ms": 1000}).files[0]
    return marked.metadata["video_metrics"]["duplicate_segments"]


def test_repeat_search_across_blocks_matches_one_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Searching earlier frames a few at a time finds exactly the same repeat."""
    path = tmp_path / "replay.mkv"
    run_tool(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", _REPLAY, "-c:v", "mpeg4", "-q:v", "2", str(path)]
    )
    file = FileItem(id="replay", path=str(path), filename=path.name, modality="video")
    whole = _duplicate_windows(tmp_path / "whole", file)
    monkeypatch.setattr(sequence, "_SEARCH_BLOCK", 7)
    assert len(whole) == 1
    assert _duplicate_windows(tmp_path / "blocks", file) == whole


def test_luma_in_blocks_matches_one_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Thumbnail luma converted a few frames at a time equals one whole conversion."""
    frames = 10
    rng = np.random.default_rng(7)
    thumbnails = rng.integers(
        0,
        256,
        (frames, analysis.THUMBNAIL_HEIGHT, analysis.THUMBNAIL_WIDTH, 3),
        dtype=np.uint8,
    )
    zeros = np.zeros(frames, dtype=np.float64)
    measured = analysis.VideoAnalysis(
        rate=10.0,
        frame_ms=100.0,
        duration_ms=1000,
        mean=zeros,
        deviation=zeros,
        detail=zeros,
        change=zeros,
        peak=zeros,
        shift=zeros,
        thumbnails=thumbnails,
    )
    weights = np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
    expected = thumbnails.reshape(frames, -1, 3).astype(np.float32) @ weights
    monkeypatch.setattr(analysis, "_LUMA_BLOCK", 3)
    assert np.array_equal(measured.luma(), expected)
