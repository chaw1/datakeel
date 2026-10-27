# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local-only command failures and deterministic media artifact provenance."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import EmptyParams
from datakeel.operators.media.tools import (
    decode_audio,
    media_artifact,
    probe_file,
    run_tool,
    run_tool_stderr,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_missing_ffmpeg_explains_user_install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing external tools fail with an actionable installation command."""

    def unavailable(_program: str) -> None:
        return None

    monkeypatch.setattr("datakeel.operators.media.tools.shutil.which", unavailable)
    with pytest.raises(ExecutionError, match="brew install ffmpeg"):
        run_tool(["ffmpeg", "-version"])


def test_commands_reject_unlisted_programs() -> None:
    """The command adapter accepts only the two documented external tools."""
    with pytest.raises(ValidationError, match="ffmpeg or ffprobe"):
        run_tool(["arbitrary-command"])


def test_timeout_is_a_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung decoder becomes a bounded, explicit execution failure."""

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = "ffmpeg"
        raise subprocess.TimeoutExpired(command, 300)

    monkeypatch.setattr("datakeel.operators.media.tools.subprocess.run", timeout)
    with pytest.raises(ExecutionError, match="TimeoutExpired"):
        run_tool(["ffmpeg", "-version"])


def test_invalid_recording_reports_decoder_error(tmp_path: Path) -> None:
    """Corrupt bytes cannot silently produce empty measurements."""
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"generated invalid recording")
    with pytest.raises(ExecutionError, match="could not process recording"):
        probe_file(FileItem(path=str(path), filename=path.name, modality="video"))


def test_stderr_measurements_and_nested_source_ranges(tmp_path: Path) -> None:
    """Derived audio keeps root-time coordinates and deterministic artifact identities."""
    content = run_tool(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=0.2", "-f", "wav", "pipe:1"]
    )
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(content)
    source = FileItem(
        id="generated-source",
        path=str(source_path),
        filename=source_path.name,
        modality="audio",
        metadata={"source_start_ms": 500},
    )
    first = media_artifact(
        source,
        tmp_path / "first",
        content,
        "wav",
        "audio.trim_silence",
        EmptyParams(),
        start_ms=100,
        end_ms=300,
    )
    second = media_artifact(
        source,
        tmp_path / "second",
        content,
        "wav",
        "audio.trim_silence",
        EmptyParams(),
        start_ms=100,
        end_ms=300,
    )
    assert first.id == second.id
    assert first.sha256 == second.sha256
    assert first.metadata["source_start_ms"] == 600
    assert first.metadata["source_end_ms"] == 800
    assert first.metadata["media_history"][0]["version"] == "1.0.0"
    assert probe_file(first).audio_tracks == 1
    diagnostics = run_tool_stderr(
        ["ffmpeg", "-v", "info", "-f", "lavfi", "-i", "sine=d=0.2", "-f", "null", "-"]
    )
    assert b"Audio:" in diagnostics


def test_artifact_rejects_unknown_timing_options(tmp_path: Path) -> None:
    """Timing metadata cannot accept misspelled boundary fields."""
    source = FileItem(path="unused", filename="generated.wav")
    with pytest.raises(ValidationError, match="Only start_ms"):
        media_artifact(
            source, tmp_path, b"", "wav", "audio.trim_silence", EmptyParams(), end_ms=100, typo=1
        )


def test_audio_decode_honors_analysis_duration_and_alignment_source_time(tmp_path: Path) -> None:
    """Bound synchronization decoding and adjust a trimmed recording's relative lag."""
    content = run_tool(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-f", "wav", "pipe:1"]
    )
    path = tmp_path / "bounded.wav"
    path.write_bytes(content)
    source = FileItem(
        id="microphone",
        path=str(path),
        filename=path.name,
        modality="audio",
        metadata={
            "media_alignment": {
                "reference_file_id": "camera",
                "aligned": True,
                "offset_ms": 500.0,
                "confidence": 0.9,
                "reason": "matched",
            }
        },
    )
    assert decode_audio(source, max_duration_seconds=0.125).size == 2000
    trimmed = media_artifact(
        source,
        tmp_path / "trim",
        content,
        "wav",
        "audio.trim_silence",
        EmptyParams(),
        start_ms=480,
        end_ms=1000,
    )
    assert trimmed.metadata["media_alignment"]["offset_ms"] == 20.0
    assert trimmed.metadata["source_start_ms"] == 480
