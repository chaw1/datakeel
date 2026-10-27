# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check sampled interval coalescing and explicit decoder failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from datakeel.operators.video import frames

if TYPE_CHECKING:
    from tests.operators.video.conftest import VideoFactory


def test_intervals_coalesce_clip_and_filter_short_runs() -> None:
    """Half-open intervals stay within the original recording duration."""
    result = frames.intervals([True, True, False, True, True], "issue", 5, 850, 250)
    assert [(item.start_ms, item.end_ms) for item in result] == [(0, 400), (600, 850)]


def test_decode_empty_frame_output_is_explicit_failure(
    make_video: VideoFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool yielding no video must fail rather than report a healthy recording."""
    source = make_video()
    monkeypatch.setattr(frames, "run_tool", lambda _arguments: b"")
    with pytest.raises(ValidationError, match="no decodable frames"):
        frames.decode_frames(source, 5)
