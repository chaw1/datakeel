# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A copy at another frame rate and size is located to within one frame of the coarser rate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

_NTSC = "30000/1001"
_H264 = ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "50")
_WALKER = (
    "testsrc2=s=320x180:r={rate}:d=0.1,tpad=stop_mode=clone:stop_duration=12[bg];"
    "color=c=red:s=20x32:r={rate}:d=12[box];"
    "[bg][box]overlay=x='10+t*27':y='20+t*6':shortest=1"
)
# Hard cuts between generated scenes; every shot shows different luma (hue alone would not).
_SHOTS = (
    "testsrc2=s=320x180:r={rate}:d=0.7",
    "testsrc=s=320x180:r={rate}:d=20.45,trim=start=20,hflip",
    "testsrc2=s=320x180:r={rate}:d=7.85,trim=start=7,hflip",
    "testsrc=s=320x180:r={rate}:d=3.6,trim=start=3,vflip",
    "testsrc2=s=320x180:r={rate}:d=31.1,trim=start=30,negate,vflip",
    "testsrc2=s=320x180:r={rate}:d=15.5,trim=start=15,vflip",
    "testsrc=s=320x180:r={rate}:d=11.95,trim=start=11",
    "testsrc=s=320x180:r={rate}:d=40.65,trim=start=40,negate",
    "testsrc2=s=320x180:r={rate}:d=24.2,trim=start=23,negate",
)
_CUTS = (
    ";".join(
        f"{shot},setpts=PTS-STARTPTS,format=yuv420p,setsar=1[s{index}]"
        for index, shot in enumerate(_SHOTS)
    )
    + ";"
    + "".join(f"[s{index}]" for index in range(len(_SHOTS)))
    + f"concat=n={len(_SHOTS)}:v=1:a=0"
)


def _source(directory: Path, name: str, graph: str, rate: str) -> FileItem:
    path = directory / f"{name}.mp4"
    generate = ["ffmpeg", "-y", "-f", "lavfi", "-i", graph.format(rate=rate)]
    run_tool([*generate, "-r", rate, *_H264, str(path)])
    return FileItem(id=name, path=str(path), filename=path.name, modality="video")


def _copy(directory: Path, source: FileItem, span: tuple[float, float], rate: str) -> FileItem:
    """Embed ``span`` of the source, resampled and downscaled, after 3 s of other footage."""
    path = directory / "copy.mp4"
    start, end = span
    graph = (
        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,fps={rate},scale=160:90,"
        "format=yuv420p,setsar=1[copy];"
        f"color=c=gray:s=160x90:r={rate}:d=3,noise=alls=20:allf=t,format=yuv420p,setsar=1[pre];"
        f"color=c=navy:s=160x90:r={rate}:d=2,noise=alls=20:allf=t,format=yuv420p,setsar=1[post];"
        "[pre][copy][post]concat=n=3:v=1:a=0"
    )
    run_tool(
        ["ffmpeg", "-y", "-i", source.path, "-filter_complex", graph, "-r", rate, *_H264, str(path)]
    )
    return FileItem(id="copy", path=str(path), filename=path.name, modality="video")


@pytest.mark.parametrize(
    ("source_rate", "copy_rate"),
    [pytest.param(_NTSC, "25", id="29.97-to-25"), pytest.param("25", _NTSC, id="25-to-29.97")],
)
@pytest.mark.parametrize(
    ("scene", "span"),
    [
        pytest.param(_WALKER, (5.2, 11.6), id="moving-subject"),
        pytest.param(_CUTS, (2.0, 6.0), id="cuts"),
        pytest.param(_CUTS, (1.3, 4.1), id="cuts-ending-in-short-shot"),
    ],
)
def test_copy_at_another_frame_rate_is_located_to_one_frame(
    tmp_path: Path, scene: str, span: tuple[float, float], source_rate: str, copy_rate: str
) -> None:
    """25 and 29.97 fps measure motion over 80/120 and 67/100 ms; the spans must agree."""
    source = _source(tmp_path, "source", scene, source_rate)
    copy = _copy(tmp_path, source, span, copy_rate)
    marked = REGISTRY["video.dedup"].run([source, copy], tmp_path / "out", {"window_ms": 1000})
    windows = marked.files[1].metadata["video_metrics"]["duplicate_segments"]
    frame_ms = 1000 / 25
    start, end = span
    assert windows
    assert abs(windows[0]["start_ms"] - 3000) <= frame_ms, windows
    assert abs(windows[-1]["end_ms"] - (3000 + (end - start) * 1000)) <= frame_ms, windows
    covered = sum(window["end_ms"] - window["start_ms"] for window in windows)
    assert covered >= (end - start) * 1000 - frame_ms, windows
