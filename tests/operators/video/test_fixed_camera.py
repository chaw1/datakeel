# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed-camera footage: live scenes are neither frozen nor repeats; real ones are found."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

_STATIC = "testsrc2=s=160x96:r={rate}:d=0.1,tpad=stop_mode=clone:stop_duration={seconds}"
_SUBJECT = "[bg];color=c=red:s=10x16:r={rate}:d={seconds}[box];[bg][box]overlay=x='{x}':y='{y}'"
_FRAME_MS = 100


def _scene(seconds: int, x: str = "5+t*15", y: str = "30+t*3", rate: int = 10) -> str:
    """Return a static camera picture crossed by a small red subject."""
    background = _STATIC.format(rate=rate, seconds=seconds)
    return background + _SUBJECT.format(rate=rate, seconds=seconds, x=x, y=y) + ":shortest=1"


def _still(seconds: int) -> str:
    return _STATIC.format(rate=10, seconds=seconds)


def _encode(directory: Path, name: str, graph: str, *options: str) -> FileItem:
    path = directory / f"{name}.mkv"
    run_tool(["ffmpeg", "-y", "-f", "lavfi", "-i", graph, "-c:v", "mpeg4", *options, str(path)])
    return FileItem(id=name, path=str(path), filename=path.name, modality="video")


def _issues(directory: Path, file: FileItem) -> list[tuple[str, int, int]]:
    measured = REGISTRY["video.invalid_frames"].run([file], directory / "out").files[0]
    marked = REGISTRY["video.dedup"].run([measured], directory / "out", {"window_ms": 1000})
    return [
        (issue["code"], issue["start_ms"], issue["end_ms"])
        for issue in marked.files[0].metadata["media_issues"]
    ]


def test_freeze_start_is_frame_accurate_across_keyframes(tmp_path: Path) -> None:
    """Keyframes re-encoding the held picture neither delay nor split the freeze."""
    graph = (
        "testsrc2=s=160x96:r=10:d=1[a];"
        "testsrc2=s=160x96:r=10:d=1.1,trim=start=1:end=1.1,setpts=PTS-STARTPTS,"
        "tpad=stop_mode=clone:stop_duration=1.9[b];"
        "testsrc2=s=160x96:r=10:d=4,trim=start=3,setpts=PTS-STARTPTS[c];"
        "[a][b][c]concat=n=3:v=1:a=0"
    )
    # Keyframes every 0.7 s fall at 1.4 s, 2.1 s and 2.8 s inside the 1-3 s freeze.
    file = _encode(tmp_path, "keyframes", graph, "-q:v", "8", "-g", "7")
    frozen = [
        (start, end) for code, start, end in _issues(tmp_path, file) if code == "frozen_frame"
    ]
    assert len(frozen) == 1
    start, end = frozen[0]
    assert abs(start - 1000) <= _FRAME_MS
    assert abs(end - 3000) <= _FRAME_MS


@pytest.mark.parametrize(
    ("name", "graph"),
    [
        ("small-moving-target", _scene(6)),
        ("slow-lighting-change", _still(6) + ",eq=brightness='t*0.01':eval=frame"),
        ("sensor-noise", _still(6) + ",noise=alls=12:allf=t"),
        (
            "blinking-indicator",
            _still(6) + ",drawbox=x=4:y=4:w=12:h=8:color=white:t=fill:enable='lt(mod(t,1),0.5)'",
        ),
        ("fan-half-window-period", _scene(6, x="70+30*sin(2*PI*t/0.5)", y="40")),
        ("fan-longer-period", _scene(6, x="70+30*sin(2*PI*t/0.8)", y="40")),
    ],
)
def test_live_fixed_camera_is_neither_frozen_nor_repeated(
    tmp_path: Path, name: str, graph: str
) -> None:
    """A static camera with a moving subject, drifting light, noise or a blinking light."""
    issues = _issues(tmp_path, _encode(tmp_path, name, graph, "-q:v", "2"))
    assert [issue for issue in issues if issue[0] in {"frozen_frame", "video_duplicate"}] == []


def test_static_scene_without_any_change_is_not_a_repeat(tmp_path: Path) -> None:
    """Identical frames are a freeze, never a repeat of earlier footage."""
    issues = _issues(tmp_path, _encode(tmp_path, "still", _still(5), "-q:v", "2"))
    assert [code for code, _start, _end in issues] == ["frozen_frame"]


def test_replayed_fixed_camera_segment_is_located_exactly(tmp_path: Path) -> None:
    """Seconds 1-3 replayed at 5-7 s are reported with frame-accurate bounds."""
    graph = (
        _scene(8) + ",split=3[a][b][c];"
        "[a]trim=0:5,setpts=PTS-STARTPTS[x];[b]trim=1:3,setpts=PTS-STARTPTS[y];"
        "[c]trim=7:8,setpts=PTS-STARTPTS[z];[x][y][z]concat=n=3:v=1:a=0"
    )
    file = _encode(tmp_path, "replay", graph, "-q:v", "2")
    measured = REGISTRY["video.invalid_frames"].run([file], tmp_path / "out").files[0]
    marked = REGISTRY["video.dedup"].run([measured], tmp_path / "out", {"window_ms": 1000})
    windows = marked.files[0].metadata["video_metrics"]["duplicate_segments"]
    assert len(windows) == 1
    window = windows[0]
    for key, expected in (
        ("start_ms", 5000),
        ("end_ms", 7000),
        ("source_start_ms", 1000),
        ("source_end_ms", 3000),
    ):
        assert abs(window[key] - expected) <= _FRAME_MS, (key, window)
