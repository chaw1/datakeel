# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A file that stores less than its header promises is reported with its real extent."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.tools import TRUNCATION_TOLERANCE_MS, probe_file, run_tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _recording(directory: Path, name: str, source: str, codec: list[str]) -> Path:
    path = directory / name
    run_tool(["ffmpeg", "-y", "-f", "lavfi", "-i", source, *codec, str(path)])
    return path


def _cut(path: Path, fraction: float) -> FileItem:
    content = path.read_bytes()
    cut = path.with_name(f"cut-{path.name}")
    cut.write_bytes(content[: int(len(content) * fraction)])
    modality = "video" if path.suffix == ".mkv" else "audio"
    return FileItem(id=cut.stem, path=str(cut), filename=cut.name, modality=modality)


def _video(directory: Path) -> Path:
    return _recording(
        directory, "camera.mkv", "testsrc2=s=96x64:r=10:d=4", ["-c:v", "mpeg4", "-q:v", "2"]
    )


def _audio(directory: Path) -> Path:
    return _recording(
        directory,
        "voice.wav",
        "sine=frequency=440:sample_rate=16000:duration=4",
        ["-c:a", "pcm_s16le"],
    )


def _truncation(file: FileItem) -> list[tuple[int, int, str]]:
    return [
        (issue["start_ms"], issue["end_ms"], issue["severity"])
        for issue in file.metadata["media_issues"]
        if issue["code"] == "truncated_file"
    ]


def test_truncated_video_reports_readable_duration_and_missing_tail(tmp_path: Path) -> None:
    """The probe reports the readable extent; the lost tail is a critical issue."""
    probed = REGISTRY["video.probe"].run([_cut(_video(tmp_path), 0.5)], tmp_path / "o").files[0]
    probe = probed.metadata["media_probe"]
    assert probe["declared_duration_ms"] == 4000
    assert 1000 <= probe["duration_ms"] <= 3000
    assert _truncation(probed) == [(probe["duration_ms"], 4000, "critical")]


def test_truncated_wav_is_detected_from_its_data_chunk(tmp_path: Path) -> None:
    """A WAV header's data size is the promise even though ffprobe clamps its duration."""
    probed = REGISTRY["audio.probe"].run([_cut(_audio(tmp_path), 0.5)], tmp_path / "o").files[0]
    probe = probed.metadata["media_probe"]
    assert probe["declared_duration_ms"] == 4000
    assert probe["duration_ms"] == pytest.approx(2000, abs=50)
    assert _truncation(probed) == [(probe["duration_ms"], 4000, "critical")]


@pytest.mark.parametrize("make", [_video, _audio])
def test_complete_recording_has_no_truncation(tmp_path: Path, make: Callable[[Path], Path]) -> None:
    """An intact file keeps its header duration and gains no truncation issue."""
    path = make(tmp_path)
    file = FileItem(path=str(path), filename=path.name, modality="audio")
    probe = probe_file(file)
    assert probe.duration_ms == 4000
    assert probe.declared_duration_ms is None


def test_shortfall_within_tolerance_is_not_truncation(tmp_path: Path) -> None:
    """Losing less than the tolerance (container rounding, a partial last block) is ignored."""
    lost_fraction = (TRUNCATION_TOLERANCE_MS / 2) / 4000
    cut = _cut(_audio(tmp_path), 1 - lost_fraction)
    probed = REGISTRY["audio.probe"].run([cut], tmp_path / "o").files[0]
    assert probed.metadata["media_probe"]["declared_duration_ms"] is None
    assert _truncation(probed) == []


def test_truncation_survives_later_measurements(tmp_path: Path) -> None:
    """Invalid-frame measurement keeps the truncation another operator recorded."""
    probed = REGISTRY["video.probe"].run([_cut(_video(tmp_path), 0.5)], tmp_path / "o").files[0]
    measured = REGISTRY["video.invalid_frames"].run([probed], tmp_path / "o").files[0]
    assert len(_truncation(measured)) == 1
    again = REGISTRY["video.probe"].run([measured], tmp_path / "o").files[0]
    assert len(_truncation(again)) == 1
