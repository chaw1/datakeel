# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Each freeze rule on its own: local change, the recording's noise floor, drift."""

from __future__ import annotations

import numpy as np

from datakeel.operators.video.analysis import THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, VideoAnalysis
from datakeel.operators.video.freeze import frozen_runs
from datakeel.operators.video.invalid_frames import InvalidFramesParams

_FRAMES = 40


def _analysis(
    change: list[float], peak: list[float] | None = None, brightness: list[float] | None = None
) -> VideoAnalysis:
    """Build per-frame statistics for a 10 fps recording of one mid-grey picture."""
    count = len(change)
    levels = np.full(count, 128.0) if brightness is None else np.asarray(brightness)
    thumbnails = np.broadcast_to(
        np.round(levels).astype(np.uint8)[:, None, None, None],
        (count, THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, 3),
    ).copy()
    values = np.asarray(change, dtype=np.float64)
    return VideoAnalysis(
        rate=10.0,
        frame_ms=100.0,
        duration_ms=count * 100,
        mean=levels.astype(np.float64),
        deviation=np.full(count, 50.0),
        detail=np.full(count, 100.0),
        change=values,
        peak=values.copy() if peak is None else np.asarray(peak, dtype=np.float64),
        shift=np.zeros(count),
        thumbnails=thumbnails,
    )


def _runs(analysis: VideoAnalysis) -> list[tuple[int, int]]:
    uniform = np.zeros(analysis.frame_count, dtype=np.bool_)
    return frozen_runs(analysis, uniform, InvalidFramesParams())


def test_small_subject_in_a_still_scene_ends_the_freeze() -> None:
    """A distant subject barely moves the frame mean but changes one block a lot."""
    change = [0.0] * _FRAMES
    peak = [0.0] * _FRAMES
    for index in range(10, 21):
        change[index], peak[index] = 0.05, 8.0
    assert _runs(_analysis(change, peak)) == [(0, 9), (20, 39)]


def test_live_noise_below_the_freeze_threshold_is_not_frozen() -> None:
    """A camera's own diffuse noise keeps it live; only a stretch far below it is held."""
    change = [0.5] * _FRAMES
    assert _runs(_analysis(change)) == []
    for index in range(15, 31):
        change[index] = 0.0
    assert _runs(_analysis(change)) == [(14, 30)]


def test_held_run_never_drifts_from_its_first_picture() -> None:
    """Steps too small to notice one by one still add up to a different picture."""
    analysis = _analysis(
        [0.004] * _FRAMES, brightness=[100 + index / 4 for index in range(_FRAMES)]
    )
    runs = _runs(analysis)
    assert len(runs) > 1
    levels = analysis.thumbnails[:, 0, 0, 0].astype(np.float64)
    limit = InvalidFramesParams().freeze_difference
    assert all(levels[last] - levels[first] <= limit for first, last in runs)
