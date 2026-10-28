# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Each frame-matching rule on its own: same change, and no large local difference."""

from __future__ import annotations

import numpy as np

from datakeel.operators.video.dedup import DedupParams
from datakeel.operators.video.sequence import Sequence, frame_matches

_PIXELS = 18 * 32 * 3
_SEARCH = 9 * 16


def _frame(file_id: str, motion: float, texture: np.ndarray | None = None) -> Sequence:
    """Return a one-frame sequence of a mid-grey picture changing by ``motion``."""
    pixels = np.full((1, _PIXELS), 128, dtype=np.uint8) if texture is None else texture[None]
    change = np.zeros((1, _SEARCH), dtype=np.float32)
    change[0, : _SEARCH // 2] = motion
    change[0, _SEARCH // 2 :] = -motion
    return Sequence(
        file_id=file_id,
        times=np.zeros(1),
        frame_ms=100.0,
        textures=pixels,
        brightness=pixels.mean(axis=1, dtype=np.float64),
        hashes=np.zeros(1, dtype=np.uint64),
        duration_ms=100,
        search=np.full((1, _SEARCH), 128.0, dtype=np.float32),
        motion=change,
        moving=np.asarray([motion != 0], dtype=np.bool_),
        measured=np.ones(1, dtype=np.bool_),
    )


def test_alike_frames_that_change_differently_do_not_match() -> None:
    """A static scene looks the same throughout; only the same change is the same footage."""
    limits = DedupParams()
    prior = _frame("prior", 10.0)
    assert frame_matches(_frame("same", 10.0), 0, prior, 0.0, limits)
    opposite = _frame("opposite", -10.0)
    assert not frame_matches(opposite, 0, prior, 0.0, limits)
    assert frame_matches(opposite, 0, prior, 0.0, limits, motion=False)


def test_one_strongly_changed_spot_breaks_a_match() -> None:
    """A subject appearing in one spot barely moves the mean but is a different picture."""
    texture = np.full(_PIXELS, 128, dtype=np.uint8)
    texture[:3] = 228
    changed = _frame("changed", 10.0, texture)
    prior = _frame("prior", 10.0)
    limits = DedupParams()
    assert float(np.abs(changed.textures.astype(np.float32) - 128).mean()) < 1
    assert not frame_matches(changed, 0, prior, 0.0, limits)
    assert frame_matches(changed, 0, prior, 0.0, DedupParams(max_local_difference=255))
