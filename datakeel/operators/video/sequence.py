# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frame-accurate thumbnail sequences that locate repeated video at any time offset.

A repeat must reproduce how the picture *changes*, not only how it looks: a static
camera shows nearly the same picture all the time, so similar-looking frames are
no evidence of repeated footage. Windows that are mostly static are never
matched, a match must also reproduce the window's motion (its picture changes over ~100 ms)
closely relative to the motion's own size, and a window whose content already
recurs within one window length (periodic content in a static scene) is never
reported as a repeat.
"""

from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING, NamedTuple, Protocol

import numpy as np

from datakeel.operators.video.analysis import THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, analyse

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.models import FileItem

_CHECKS = 8
_SEARCH_HEIGHT = 9
_SEARCH_WIDTH = 16
_MOTION_STEP_MS = 100.0
# A frame moves when some 16x9 luma pixel changes by more than this many 8-bit levels
# over the motion step; codec noise in a static picture stays well below it.
_MOTION_FLOOR = 2.0
# Share of a window's frames that must be moving for the window to count as footage;
# a static scene with occasional changes (a clock ticking, a light switching) is not.
_MOVING_SHARE = 0.5
# Motion residual relative to the motion energy of both frames; uncorrelated motion
# (or noise) gives about 1, a repeat of the same motion close to 0.
_MOTION_RESIDUAL = 0.5
_CANDIDATES = 8
# Prior frames compared at once when searching for a repeat's lead frame.
_SEARCH_BLOCK = 4096
_HASH_ROWS = 8
_HASH_COLUMNS = 9
_MIN_ENERGY = 1e-6
# Further copies of a window, at multiples of one short lag, that make it periodic.
_PERIODIC_COPIES = 2
# How many windows on either side are searched for further copies of a window.
_PERIODIC_REACH = 3
# Real periods jitter by up to this much, so lags this close belong to one copy.
_PERIOD_JITTER_MS = 200.0


class Thresholds(Protocol):
    """Expose the per-frame similarity limits shared by matching and extension."""

    max_hamming: float
    max_brightness_difference: float
    max_spatial_difference: float
    max_local_difference: float


class Sequence(NamedTuple):
    """Hold every analysed frame of one recording on its own constant-rate timeline."""

    file_id: str
    times: NDArray[np.float64]
    frame_ms: float
    textures: NDArray[np.uint8]
    brightness: NDArray[np.float64]
    hashes: NDArray[np.uint64]
    duration_ms: int
    search: NDArray[np.float32]
    motion: NDArray[np.float32]
    moving: NDArray[np.bool_]
    measured: NDArray[np.bool_]
    # Motion over the other whole number of frames around 100 ms (equal to ``motion``
    # when 100 ms is a whole number of frames), for copies at a different frame rate.
    alternate: NDArray[np.float32]


class Match(NamedTuple):
    """Pair a candidate frame range with the prior frames that repeat it."""

    prior: Sequence
    first: int
    stop: int
    prior_first: int
    prior_last: int


def _resampler(source: int, target: int) -> NDArray[np.float32]:
    """Return a bilinear resampling matrix of shape ``(target, source)``."""
    positions = (np.arange(target) + 0.5) * source / target - 0.5
    lower = np.clip(np.floor(positions).astype(np.int64), 0, source - 1)
    upper = np.clip(lower + 1, 0, source - 1)
    weight = np.clip(positions - lower, 0, 1).astype(np.float32)
    matrix = np.zeros((target, source), dtype=np.float32)
    np.add.at(matrix, (np.arange(target), lower), 1 - weight)
    np.add.at(matrix, (np.arange(target), upper), weight)
    return matrix


def _dhashes(luma: NDArray[np.float32]) -> NDArray[np.uint64]:
    rows = _resampler(THUMBNAIL_HEIGHT, _HASH_ROWS)
    columns = _resampler(THUMBNAIL_WIDTH, _HASH_COLUMNS)
    small = np.einsum("rh,nhw,cw->nrc", rows, luma, columns)
    bits = (small[:, :, 1:] > small[:, :, :-1]).reshape(len(luma), -1)
    return np.packbits(bits, axis=1).view(">u8").reshape(-1).astype(np.uint64)


def decode_sequence(file: FileItem, max_fps: float) -> Sequence:
    """Build a sequence from the shared single-pass analysis at up to ``max_fps``."""
    analysis = analyse(file, max_fps)
    count = analysis.frame_count
    luma = analysis.luma().reshape(count, THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH)
    search = (
        luma.reshape(count, _SEARCH_HEIGHT, 2, _SEARCH_WIDTH, 2)
        .mean(axis=(2, 4))
        .reshape(count, -1)
    )
    step = motion_step(analysis.frame_ms)
    later = np.arange(count) + step
    motion = _change(search, step)
    textures = analysis.thumbnails.reshape(count, -1)
    return Sequence(
        file_id=file.id,
        times=np.arange(count, dtype=np.float64) * analysis.frame_ms,
        frame_ms=analysis.frame_ms,
        textures=textures,
        brightness=textures.mean(axis=1, dtype=np.float64),
        hashes=_dhashes(luma),
        duration_ms=analysis.duration_ms,
        search=search,
        motion=motion,
        moving=np.abs(motion).max(axis=1) > _MOTION_FLOOR,
        measured=later < count,
        alternate=_change(search, alternate_step(analysis.frame_ms)),
    )


def _change(search: NDArray[np.float32], step: int) -> NDArray[np.float32]:
    """Return each frame's picture change ``step`` frames ahead, without uniform brightness.

    A uniform brightness change (lighting, exposure) carries no evidence of footage.
    """
    later = np.minimum(np.arange(len(search)) + step, len(search) - 1)
    change = search[later] - search
    return (change - change.mean(axis=1, keepdims=True)).astype(np.float32)


def alternate_step(frame_ms: float) -> int:
    """Return the whole number of frames on the other side of 100 ms from ``motion_step``."""
    span = round(_MOTION_STEP_MS / frame_ms, 6)
    step = motion_step(frame_ms)
    return max(1, math.floor(span) if step > span else math.ceil(span))


def _motion_matches(candidate: Sequence, index: int, prior: Sequence, target: int) -> bool:
    """Require the same picture change, unless both are static or one runs off the end."""
    if not (candidate.measured[index] and prior.measured[target]):
        return True
    if not candidate.moving[index] and not prior.moving[target]:
        return True
    if math.isclose(candidate.frame_ms, prior.frame_ms):
        return _same_change(candidate.motion[index], prior.motion[target])
    # 100 ms is rarely a whole number of frames at both rates (25 fps: 80 or 120 ms;
    # 29.97 fps: 67 or 100 ms), so the closest pair of spans is compared.
    return any(
        _same_change(left[index], right[target])
        for left in (candidate.motion, candidate.alternate)
        for right in (prior.motion, prior.alternate)
    )


def _same_change(left: NDArray[np.float32], right: NDArray[np.float32]) -> bool:
    energy = float(left @ left + right @ right)
    residual = float(np.square(left - right).sum())
    return residual <= _MOTION_RESIDUAL * energy


def motion_step(frame_ms: float) -> int:
    """Return how many frames ahead a frame's motion is measured (about 100 ms)."""
    return max(1, round(round(_MOTION_STEP_MS / frame_ms, 6)))


def frame_matches(
    candidate: Sequence,
    index: int,
    prior: Sequence,
    target_ms: float,
    limits: Thresholds,
    *,
    motion: bool = True,
) -> bool:
    """Compare one frame with the prior frames around its mapped time, tolerating one frame.

    ``motion=False`` compares appearance only, for the last frames of a repeat whose
    motion is measured against frames after the repeat ends.
    """
    nearest = int(np.clip(round(target_ms / prior.frame_ms), 0, len(prior.times) - 1))
    if abs(prior.times[nearest] - target_ms) > prior.frame_ms:
        return False
    neighbours = range(max(0, nearest - 1), min(len(prior.times), nearest + 2))
    return any(
        _looks_same(candidate, index, prior, other, limits)
        and (not motion or _motion_matches(candidate, index, prior, other))
        for other in neighbours
    )


def _looks_same(
    candidate: Sequence, index: int, prior: Sequence, other: int, limits: Thresholds
) -> bool:
    difference = np.abs(prior.textures[other].astype(np.float32) - candidate.textures[index])
    hamming = int(np.bitwise_count(prior.hashes[other] ^ candidate.hashes[index]))
    return (
        float(difference.mean()) <= limits.max_spatial_difference
        and float(difference.max()) <= limits.max_local_difference
        and hamming <= limits.max_hamming
        and abs(prior.brightness[other] - candidate.brightness[index])
        <= limits.max_brightness_difference
    )


def _lead_candidates(
    candidate: Sequence, lead: int, prior: Sequence, limit: int, limits: Thresholds
) -> NDArray[np.int64]:
    """Return prior frames whose appearance and motion both resemble the lead frame.

    Prior frames are compared in fixed-size blocks: one temporary per lead sized by
    the whole prior recording would grow with its length, and allocators keep such
    differently sized buffers, so a long recording's memory would keep rising.
    """
    target, change = candidate.search[lead], candidate.motion[lead]
    reach = (2 * limits.max_spatial_difference) ** 2
    own = float(change @ change)
    rows: list[NDArray[np.int64]] = []
    keys: list[NDArray[np.float32]] = []
    for start in range(0, limit, _SEARCH_BLOCK):
        looks = prior.search[start : start + _SEARCH_BLOCK][: limit - start]
        moves = prior.motion[start : start + _SEARCH_BLOCK][: limit - start]
        appearance = np.square(looks - target).mean(axis=1)
        energy = np.square(moves).sum(axis=1) + own
        residual = np.square(moves - change).sum(axis=1)
        found = np.flatnonzero((appearance <= reach) & (residual <= _MOTION_RESIDUAL * energy))
        rows.append(found + start)
        keys.append(appearance[found] + residual[found] / np.maximum(energy[found], _MIN_ENERGY))
    if not rows:
        return np.zeros(0, dtype=np.int64)
    found = np.concatenate(rows)
    order = np.argsort(np.concatenate(keys))
    return found[order[:_CANDIDATES]]


def find_match(
    candidate: Sequence,
    window: tuple[int, int],
    priors: list[tuple[Sequence, int]],
    limits: Thresholds,
) -> Match | None:
    """Find the closest prior frame range repeating every sampled frame of a moving window."""
    first, stop = window
    if candidate.moving[first:stop].mean() < _MOVING_SHARE:
        return None
    lead = first + int(np.argmax(np.abs(candidate.motion[first:stop]).max(axis=1)))
    checks = np.unique(np.linspace(first, stop - 1, num=min(_CHECKS, stop - first)).round())
    checks = checks.astype(np.int64)
    best: tuple[float, Match] | None = None
    for prior, limit in priors:
        for row in _lead_candidates(candidate, lead, prior, limit, limits).tolist():
            delta = prior.times[row] - candidate.times[lead]
            mapped = np.rint((candidate.times[checks] + delta) / prior.frame_ms).astype(np.int64)
            if mapped[0] < 0 or mapped[-1] >= limit:
                continue
            score = _window_score(candidate, checks, prior, mapped, limits)
            if score is not None and (best is None or score < best[0]):
                best = (score, Match(prior, first, stop, int(mapped[0]), int(mapped[-1])))
    if best is None or _recurs_within(candidate, checks, stop - first, limits):
        return None
    return best[1]


def _recurs_within(
    candidate: Sequence, checks: NDArray[np.int64], span: int, limits: Thresholds
) -> bool:
    """Report whether the window keeps recurring nearby, as periodic content does.

    Content that cycles with a period no longer than the window (a blinking light,
    a fan, a flickering lamp, a running clock's sub-second digits) is a stationary
    scene: it matches its own recording again and again, so a match elsewhere is no
    evidence of repeated footage. A clip copied once has a single nearby copy; a
    window with two or more separate copies within three windows on either side is
    periodic. Lags shorter than half a window are not tested, because smooth motion
    looks alike over short lags; lags within a period's jitter (about 200 ms, at least
    two frames) are one copy, so a period of half a window still counts as periodic.
    """
    lags = range(max(2, (span + 1) // 2), _PERIODIC_REACH * span + 1)
    offsets = [offset for lag in lags for offset in (-lag, lag)]
    found = sorted(offset for offset in offsets if _recurs(candidate, checks, offset, limits))
    jitter = max(2, round(_PERIOD_JITTER_MS / candidate.frame_ms))
    separate = sum(1 for before, after in itertools.pairwise(found) if after - before > jitter)
    return bool(found) and separate + 1 >= _PERIODIC_COPIES


def _recurs(
    candidate: Sequence, checks: NDArray[np.int64], offset: int, limits: Thresholds
) -> bool:
    """Report a near copy of the window, allowing one missed check in eight.

    Periodic content often carries a slowly changing part (a clock's seconds) that
    breaks single checks; a near copy is enough evidence that the window cycles.
    """
    shifted = checks + offset
    if shifted[0] < 0 or shifted[-1] >= len(candidate.times):
        return False
    misses = sum(
        not frame_matches(candidate, index, candidate, float(candidate.times[target]), limits)
        for index, target in zip(checks.tolist(), shifted.tolist(), strict=True)
    )
    return misses <= len(checks) // _CHECKS


def _window_score(
    candidate: Sequence,
    checks: NDArray[np.int64],
    prior: Sequence,
    mapped: NDArray[np.int64],
    limits: Thresholds,
) -> float | None:
    residuals: list[float] = []
    for index, target in zip(checks.tolist(), mapped.tolist(), strict=True):
        if not frame_matches(candidate, index, prior, float(prior.times[target]), limits):
            return None
        # Score the exact mapping so the true offset beats a neighbouring tolerated one.
        texture = candidate.textures[index].astype(np.float32)
        residuals.append(float(np.abs(prior.textures[target].astype(np.float32) - texture).mean()))
    return float(np.mean(residuals))
