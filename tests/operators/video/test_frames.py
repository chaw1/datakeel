# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check sampled interval coalescing and frame timestamps read from packets."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.operators.video import frames

if TYPE_CHECKING:
    from tests.operators.video.conftest import VideoFactory


def test_intervals_coalesce_clip_and_filter_short_runs() -> None:
    """Half-open intervals stay within the original recording duration."""
    result = frames.intervals([True, True, False, True, True], "issue", 5, 850, 250)
    assert [(item.start_ms, item.end_ms) for item in result] == [(0, 400), (600, 850)]


def test_frame_times_come_from_kept_packets_in_presentation_order(
    make_video: VideoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Packet times are sorted out of decode order; discarded packets are not frames."""
    source = make_video()
    listing = b"0.200000,__\n0.100000,K_\n0.300000,_D\n0.400000,__\n"
    monkeypatch.setattr(frames, "run_tool", lambda _arguments, **_options: listing)
    assert frames.frame_times(source) == pytest.approx([0.0, 100.0, 300.0])


def test_frame_times_without_packet_stamps_decode_frames(
    make_video: VideoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream without packet timestamps falls back to decoded frame times."""
    source = make_video("testsrc2=size=96x64:rate=5:duration=1")
    calls: list[str] = []

    def tool(arguments: list[str], timeout: float) -> bytes:
        assert timeout > 0
        calls.append(arguments[arguments.index("-show_entries") + 1])
        return b"N/A,K_\n" if arguments[5].startswith("packet") else b"1.5\n1.7\nN/A\n"

    monkeypatch.setattr(frames, "run_tool", tool)
    assert frames.frame_times(source) == pytest.approx([0.0, 200.0])
    assert calls == ["packet=pts_time,flags", "frame=best_effort_timestamp_time"]


def test_frame_times_without_any_frames_is_explicit_failure(
    make_video: VideoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool yielding no video frames must fail rather than report a healthy recording."""
    source = make_video("testsrc2=size=96x64:rate=5:duration=0.6")
    monkeypatch.setattr(frames, "run_tool", lambda _arguments, **_options: b"")
    with pytest.raises(ValidationError, match="no timestamped frames"):
        frames.frame_times(source)


def test_frame_times_of_missing_recording_is_execution_failure(
    make_video: VideoFactory,
) -> None:
    """A recording removed after registration is reported, not crashed on."""
    source = make_video("testsrc2=size=96x64:rate=5:duration=0.4")
    Path(source.path).unlink()
    with pytest.raises(ExecutionError, match="not readable"):
        frames.frame_times(source)
