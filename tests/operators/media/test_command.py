# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Long recordings get time budgets that scale with them, and streams fail explicitly."""

from __future__ import annotations

import subprocess

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.operators.media import command
from datakeel.operators.media.command import decoder_threads, media_timeout, run_tool, stream_tool


def test_timeout_scales_with_duration_and_resolution() -> None:
    """Base plus twice the duration at 1080p or below; larger frames scale the share."""
    assert media_timeout(0) == 300
    assert media_timeout(30 * 60 * 1000, 1920, 1080) == 300 + 2 * 1800
    assert media_timeout(30 * 60 * 1000, 640, 360) == 300 + 2 * 1800
    assert media_timeout(10 * 60 * 1000, 3840, 2160) == 300 + 2 * 600 * 4


def test_timeout_settings_are_configurable_and_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Base, ratio and cap come from the environment; the cap bounds any recording."""
    monkeypatch.setenv("DATAKEEL_MEDIA_TIMEOUT_BASE_SECONDS", "10")
    monkeypatch.setenv("DATAKEEL_MEDIA_TIMEOUT_RATIO", "0.5")
    monkeypatch.setenv("DATAKEEL_MEDIA_TIMEOUT_MAX_SECONDS", "100")
    assert media_timeout(60_000) == 10 + 0.5 * 60
    assert media_timeout(24 * 3600 * 1000, 7680, 4320) == 100


def test_decoder_threads_default_to_bounded_cpu_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Automatic threading uses the CPU count up to eight; a setting overrides it."""
    monkeypatch.setattr(command.os, "cpu_count", lambda: 32)
    assert decoder_threads() == 8
    monkeypatch.setattr(command.os, "cpu_count", lambda: None)
    assert decoder_threads() == 1
    monkeypatch.setenv("DATAKEEL_MEDIA_THREADS", "3")
    assert decoder_threads() == 3


def test_ffmpeg_decodes_with_threads_and_receives_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The thread count goes to ffmpeg only; every command gets the caller's budget."""
    monkeypatch.setenv("DATAKEEL_MEDIA_THREADS", "4")
    calls: list[tuple[list[str], object]] = []

    def run(arguments: list[str], **options: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((arguments, options["timeout"]))
        return subprocess.CompletedProcess(arguments, 0, b"out", b"")

    monkeypatch.setattr(command.subprocess, "run", run)
    assert run_tool(["ffmpeg", "-version"], timeout=42.0) == b"out"
    run_tool(["ffprobe", "-version"])
    ffmpeg, ffprobe = calls
    assert ffmpeg[0][3:9] == ["-nostdin", "-threads", "4", "-filter_threads", "4", "-version"]
    assert ffmpeg[1] == 42.0
    assert "-threads" not in ffprobe[0]
    assert ffprobe[1] == 300


def _frames(source: str, chunk: int, timeout: float = 30.0) -> list[bytes]:
    arguments = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source]
    arguments.extend(["-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    return list(stream_tool(arguments, chunk, timeout=timeout))


def test_stream_yields_whole_records() -> None:
    """Each decoded frame arrives as one fixed-size record."""
    records = _frames("testsrc2=s=16x8:r=10:d=1", 16 * 8)
    assert len(records) == 10
    assert {len(record) for record in records} == {128}


def test_stream_with_trailing_partial_record_fails() -> None:
    """Output that does not divide into records is a failure, not a silent drop."""
    with pytest.raises(ExecutionError, match="truncated output record"):
        _frames("testsrc2=s=16x8:r=10:d=1", 16 * 8 * 3)


def test_stream_command_failure_reports_its_diagnostic() -> None:
    """A failing command raises with ffmpeg's own message."""
    with pytest.raises(ExecutionError, match="could not process recording"):
        _frames("nosuchsource=d=1", 128)


def test_stream_past_its_budget_is_killed() -> None:
    """A command still running when its budget expires is stopped and reported."""
    arguments = ["ffmpeg", "-v", "error", "-re", "-f", "lavfi", "-i", "testsrc2=s=16x8:r=10:d=30"]
    arguments.extend(["-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    with pytest.raises(ExecutionError, match="TimeoutExpired"):
        list(stream_tool(arguments, 128, timeout=0.5))
