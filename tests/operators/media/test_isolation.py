# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One recording's failure is recorded on that recording and never stops the others."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.media.isolation import has_failed, mark_failed
from tests.operators.media.helpers import audio_file, failure_reason

if TYPE_CHECKING:
    from pathlib import Path


def _broken(directory: Path, name: str = "broken") -> FileItem:
    path = directory / f"{name}.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 64)
    return FileItem(id=name, path=str(path), filename=path.name, modality="audio")


def test_failed_recording_is_marked_and_others_are_processed(tmp_path: Path) -> None:
    """A per-recording operator processes healthy files and marks only the broken one."""
    good = audio_file(tmp_path, "good", "sine=frequency=440:duration=1")
    result = REGISTRY["audio.probe"].run([_broken(tmp_path), good], tmp_path / "out")
    by_id = {file.id: file for file in result.files}
    assert "could not process" in failure_reason(by_id["broken"], "audio.probe")
    assert not has_failed(by_id["good"])
    assert by_id["good"].metadata["media_probe"]["duration_ms"] == 1000
    assert result.quality["failed_files"] == ["broken"]
    assert result.quality["input_count"] == 2
    assert result.quality["output_count"] == 2
    assert result.quality["removed_count"] == 0


def test_failed_recording_passes_later_operators_untouched(tmp_path: Path) -> None:
    """Later operators neither retry nor re-mark a recording that already failed."""
    failed = mark_failed(_broken(tmp_path), "audio.probe", ValueError("unreadable"))
    result = REGISTRY["audio.loudness"].run([failed], tmp_path / "out")
    assert result.files == [failed]
    assert failure_reason(result.files[0], "audio.probe") == "ValueError: unreadable"
    assert result.quality["failed_files"] == []
    assert "media_history" not in result.files[0].metadata


def test_pairwise_operator_isolates_a_recording_it_cannot_decode(tmp_path: Path) -> None:
    """Deduplication compares the readable recordings and marks the unreadable one."""
    first = audio_file(tmp_path, "first", "sine=frequency=440:duration=1")
    second = audio_file(tmp_path, "second", "sine=frequency=660:duration=1")
    broken = _broken(tmp_path)
    result = REGISTRY["audio.dedup"].run([first, broken, second], tmp_path / "out")
    assert [file.id for file in result.files] == ["first", "broken", "second"]
    assert failure_reason(result.files[1], "audio.dedup")
    assert result.quality["failed_files"] == ["broken"]


def test_failure_reason_is_bounded(tmp_path: Path) -> None:
    """A long diagnostic is truncated so one recording cannot bloat the manifest."""
    failed = mark_failed(_broken(tmp_path), "video.probe", ValueError("x" * 5000))
    assert len(failure_reason(failed, "video.probe")) == 1000
