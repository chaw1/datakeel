# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Relative recording names reach ffmpeg as files, never as options or protocols."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import run_tool
from tests.operators.media.helpers import audio_file

if TYPE_CHECKING:
    from pathlib import Path

AWKWARD_NAMES = ("-take", "cam:1", "pipe:0")


def _relative_copies(tmp_path: Path, source: Path, suffix: str) -> list[FileItem]:
    modality = "video" if suffix == ".mp4" else "audio"
    files: list[FileItem] = []
    for name in AWKWARD_NAMES:
        shutil.copyfile(source, tmp_path / f"{name}{suffix}")
        files.append(
            FileItem(id=name, path=f"{name}{suffix}", filename=f"{name}{suffix}", modality=modality)
        )
    return files


@pytest.mark.parametrize(
    ("operator", "params"),
    [
        ("audio.probe", {}),
        ("audio.vad", {}),
        ("audio.clipping", {}),
        ("audio.loudness", {"normalize": True}),
        ("audio.trim_silence", {}),
        ("audio.dedup", {"remove": False}),
        ("media.align", {}),
    ],
)
def test_audio_operators_read_dash_and_colon_names_as_local_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operator: str, params: dict[str, object]
) -> None:
    """A take named like an option or a protocol is decoded from the working directory."""
    source = audio_file(
        tmp_path, "source", "anoisesrc=color=violet:seed=7:amplitude=0.3:sample_rate=16000:d=1.2"
    )
    monkeypatch.chdir(tmp_path)
    files = _relative_copies(tmp_path, tmp_path / source.filename, ".wav")
    result = REGISTRY[operator].run(files, tmp_path / "out", params)
    assert result.files
    for file in result.files:
        if operator == "media.align":
            assert file.metadata["media_alignment"]["offset_ms"] == 0
        else:
            assert file.metadata["media_probe"]["duration_ms"] > 0


@pytest.mark.parametrize(
    ("operator", "params"),
    [
        ("video.probe", {}),
        ("video.invalid_frames", {}),
        ("video.dedup", {"window_ms": 500}),
        ("video.segment", {"window_ms": 500}),
        ("video.normalize", {"width": 64, "height": 48}),
    ],
)
def test_video_operators_read_dash_and_colon_names_as_local_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operator: str, params: dict[str, object]
) -> None:
    """Probing, frame timing, decoding and rendering all address the named local file."""
    source = tmp_path / "source.mp4"
    run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "cellauto=s=96x64:rate=12:rule=30:seed=2,trim=duration=1",
            "-c:v",
            "mpeg4",
            str(source),
        ]
    )
    monkeypatch.chdir(tmp_path)
    files = _relative_copies(tmp_path, source, ".mp4")
    result = REGISTRY[operator].run(files, tmp_path / "out", params)
    assert result.files
    for file in result.files:
        assert file.metadata.get("media_probe", {"duration_ms": 1})["duration_ms"] > 0
