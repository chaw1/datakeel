# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find held pictures frame by frame, telling a freeze from a static live camera.

A frame continues the previous picture only when nothing changed locally (no
block changed much more than the frame as a whole), any diffuse change stays
below the recording's own noise floor, and the frame still matches the first
frame of the held run. A keyframe re-encoding a frozen picture is a single,
diffuse, zero-mean blip between held frames and does not end the freeze; a small
moving subject, a slow lighting drift or live sensor noise does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from datakeel.operators.video.analysis import THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.operators.video.analysis import VideoAnalysis

_MIN_FRAMES = 2
# A re-encoding step is several times larger than the changes on either side of it.
_ISOLATION = 4.0
# Mean absolute change (8-bit levels at 160x90) treated as identical frames, and the
# largest single-frame refinement an encoder applies to a held picture.
_IDENTICAL = 0.005
_SETTLE = 0.1
_QUIET_WINDOW = 9
# Largest keyframe re-encoding step, as a share of the frame's luma deviation.
_REENCODING = 0.05


class FreezeLimits(Protocol):
    """Expose the thresholds that decide whether a frame repeats a held picture."""

    freeze_difference: float
    freeze_local_difference: float
    freeze_locality: float
    freeze_noise_ratio: float


def _localized(
    peak: NDArray[np.float64], spread: NDArray[np.float64], limits: FreezeLimits
) -> NDArray[np.bool_]:
    """Flag changes concentrated in part of the picture, as a moving subject is."""
    return peak > np.maximum(limits.freeze_local_difference, limits.freeze_locality * spread)


def _quiet(change: NDArray[np.float64], limits: FreezeLimits) -> NDArray[np.bool_]:
    """Flag frames whose neighbourhood changes far less than the recording usually does.

    A live static camera keeps changing at its own noise level, so only stretches
    well below the recording's median change, or essentially identical frames, are
    quiet. Medians over the frames just before or just after each frame ignore the
    few frames an encoder spends refining a picture after a cut or a keyframe.
    """
    pairs = change[1:]
    floor = max(limits.freeze_noise_ratio * float(np.median(pairs)), _IDENTICAL)
    reach = _QUIET_WINDOW - 1
    before = np.median(
        sliding_window_view(np.pad(pairs, (reach, 0), mode="edge"), _QUIET_WINDOW), axis=1
    )
    after = np.median(
        sliding_window_view(np.pad(pairs, (0, reach), mode="edge"), _QUIET_WINDOW), axis=1
    )
    quiet = (np.minimum(before, after) <= floor) & (pairs <= max(floor, _SETTLE))
    return np.concatenate(([False], quiet))


def held_frames(
    analysis: VideoAnalysis, uniform: NDArray[np.bool_], limits: FreezeLimits
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Return whether each frame repeats the previous picture, and isolated re-encodings.

    The second mask marks a single diffuse, zero-mean step between otherwise
    unchanged frames, as a keyframe re-encoding a held picture produces.
    """
    change, shift = analysis.change, analysis.shift
    count = analysis.frame_count
    if count < _MIN_FRAMES:
        empty = np.zeros(count, dtype=np.bool_)
        return empty, empty
    spread = ~_localized(analysis.peak, change, limits)
    diffuse = spread & (change <= limits.freeze_difference)
    strict = diffuse & _quiet(change, limits)
    neighbours = np.zeros(count, dtype=np.float64)
    neighbours[1:-1] = np.maximum(change[:-2], change[2:])
    # Re-encoding noise is a few percent of the picture's own contrast; a cut to a
    # different picture changes pixels by a large share of it.
    reencoded = change <= np.maximum(limits.freeze_difference, _REENCODING * analysis.deviation)
    blip = (
        spread
        & reencoded
        & (np.abs(shift) <= change / 2)
        & (change > _ISOLATION * neighbours)
        & np.concatenate(([False], strict[:-2] & strict[2:], [False]))
    )
    held = (strict | blip) & ~uniform
    held[1:] &= ~uniform[:-1]
    held[0] = False
    return held, blip


def _same_picture(
    anchor: NDArray[np.float32], frame: NDArray[np.float32], limits: FreezeLimits
) -> bool:
    """Compare thumbnails on the 16x9 block grid that ``freeze_local_difference`` uses."""
    difference = np.abs(_blocks(frame) - _blocks(anchor))
    spread = float(difference.mean())
    if spread > limits.freeze_difference:
        return False
    return float(difference.max()) <= max(
        limits.freeze_local_difference, limits.freeze_locality * spread
    )


def _blocks(luma: NDArray[np.float32]) -> NDArray[np.float32]:
    rows, columns = THUMBNAIL_HEIGHT // 2, THUMBNAIL_WIDTH // 2
    return luma.reshape(rows, 2, columns, 2).mean(axis=(1, 3))


def frozen_runs(
    analysis: VideoAnalysis, uniform: NDArray[np.bool_], limits: FreezeLimits
) -> list[tuple[int, int]]:
    """Return inclusive ``(first, last)`` frame ranges that show one held picture."""
    held, rebase = held_frames(analysis, uniform, limits)
    luma = analysis.luma()
    runs: list[tuple[int, int]] = []
    start: int | None = None
    anchor = 0
    for index in range(1, analysis.frame_count):
        if held[index] and start is None:
            start = anchor = index - 1
        if start is None:
            continue
        if held[index] and rebase[index]:
            # A re-encoded copy of the held picture becomes the new comparison anchor.
            anchor = index
            continue
        if held[index] and _same_picture(luma[anchor], luma[index], limits):
            continue
        runs.append((start, index - 1))
        start = None
        if held[index]:
            # A new run starts at the previous frame only if this frame still shows it.
            same = _same_picture(luma[index - 1], luma[index], limits)
            start = anchor = index - 1 if same else index
    if start is not None:
        runs.append((start, analysis.frame_count - 1))
    return [(first, last) for first, last in runs if last > first]
