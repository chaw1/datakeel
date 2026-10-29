# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find clipped peaks that lossy coding has blurred, by their shape near the track's peak.

A clipped waveform is cut flat at one ceiling. Lossy coding adds ringing and overshoot,
so the samples are no longer flat or at full scale, but averaged over 0.25 ms (shorter
than the half-cycle of the voice or instrument peaks that clip) the top is flat again.
Any smooth peak is rounded: a parabola spends about half as long within 5% of its
height as within 20%, while a flat top spends nearly the same time in both. Only
half-cycles near the track's own peak level count, and only where several flat tops
occur together, as in a clipped passage; clean and limited masters keep rounded peaks.
Signals with flat tops by design (square waves) cannot be told apart from clipping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator

    from numpy.typing import NDArray

_SMOOTH_MS = 0.25
_NEAR, _WIDE = 0.05, 0.20
# Time within 5% of the top relative to time within 20%: about 0.5 for a rounded peak.
_FLAT_SHARE = 0.75
# Half-cycles at least this share of the track's 99.9th percentile level are candidates.
_PEAK_QUANTILE = 0.999
_PEAK_SHARE = 0.85
# Flat tops needed in one window and its two neighbours; clean masters showed at most two.
_FLAT_TOPS = 4
_BLOCK = 1 << 20
_LEVELS = 4096
_LEVEL_RANGE = 2.0


def flat_tops(
    channel: NDArray[np.float32],
    sample_rate: int,
    window_ms: int,
    *,
    reference: float | None = None,
) -> NDArray[np.bool_]:
    """Flag the tops of flat half-cycles near the peak level that occur in clusters.

    The channel is processed in blocks of whole half-cycles, so memory stays a small
    multiple of the decoded channel however long the recording is.
    """
    width = smoothing_width(sample_rate)
    flagged = np.zeros(channel.shape, dtype=np.bool_)
    reference = _peak_level(channel, width) if reference is None else reference
    if reference <= 0:
        return flagged
    tops = [_block_tops(start, block, reference, width) for start, block in _blocks(channel, width)]
    if not tops:
        return flagged
    first = np.concatenate([top[0] for top in tops])
    last = np.concatenate([top[1] for top in tops])
    window = max(1, sample_rate * window_ms // 1000)
    bins = first // window
    counts = np.concatenate(([0], np.bincount(bins), [0]))
    around = counts[:-2] + counts[1:-1] + counts[2:]
    for start, stop in zip(
        first[around[bins] >= _FLAT_TOPS].tolist(),
        last[around[bins] >= _FLAT_TOPS].tolist(),
        strict=True,
    ):
        flagged[start : stop + 1] = True
    return flagged


def smoothing_width(sample_rate: int) -> int:
    """Return the shared short moving-average width used by peak shape measurements."""
    return max(1, round(sample_rate * _SMOOTH_MS / 1000))


def peak_histogram(smoothed: NDArray[np.float32]) -> NDArray[np.int64]:
    """Count levels in one already smoothed block for a track-global peak reference."""
    levels = np.minimum(np.abs(smoothed) * (_LEVELS / _LEVEL_RANGE), _LEVELS - 1).astype(np.int32)
    return np.bincount(levels, minlength=_LEVELS).astype(np.int64)


def histogram_reference(histogram: NDArray[np.int64]) -> float:
    """Return the original 99.9th-percentile reference from accumulated block counts."""
    total = int(histogram.sum())
    if not total:
        return 0.0
    index = int(np.searchsorted(np.cumsum(histogram), _PEAK_QUANTILE * total))
    return (index + 1) / (_LEVELS / _LEVEL_RANGE)


def _smoothed(
    channel: NDArray[np.float32], start: int, stop: int, width: int
) -> NDArray[np.float32]:
    """Return the moving average of ``channel[start:stop]``, using the samples around it."""
    lead = min(start, width)
    segment = channel[start - lead : stop + width]
    kernel = np.full(width, 1 / width, dtype=np.float32)
    return np.convolve(segment, kernel, mode="same")[lead : lead + stop - start]


def _blocks(channel: NDArray[np.float32], width: int) -> Iterator[tuple[int, NDArray[np.float32]]]:
    """Yield smoothed blocks that end where the smoothed signal changes sign."""
    start = 0
    while start < len(channel):
        stop = min(len(channel), start + _BLOCK)
        block = _smoothed(channel, start, stop, width)
        if stop < len(channel):
            sign = np.signbit(block)
            changes = np.flatnonzero(sign[1:] != sign[:-1])
            if len(changes):
                block = block[: changes[-1] + 1]
        yield start, block
        start += len(block)


def _peak_level(channel: NDArray[np.float32], width: int) -> float:
    """Return the smoothed track's 99.9th percentile magnitude from a level histogram."""
    histogram = np.zeros(_LEVELS, dtype=np.int64)
    for _, block in _blocks(channel, width):
        histogram += peak_histogram(block)
    return histogram_reference(histogram)


def _block_tops(
    offset: int, block: NDArray[np.float32], reference: float, width: int
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Return the first and last top sample of every flat half-cycle near the peak level."""
    magnitude = np.abs(block)
    sign = np.signbit(block)
    starts = np.concatenate(([0], np.flatnonzero(sign[1:] != sign[:-1]) + 1))
    lengths = np.diff(np.append(starts, len(block)))
    heights = np.maximum.reduceat(magnitude, starts)
    level = np.repeat(heights, lengths)
    near = np.add.reduceat(magnitude >= (1 - _NEAR) * level, starts, dtype=np.int64)
    wide_mask = magnitude >= (1 - _WIDE) * level
    wide = np.add.reduceat(wide_mask, starts, dtype=np.int64)
    flat = (heights >= _PEAK_SHARE * reference) & (wide >= width) & (near >= _FLAT_SHARE * wide)
    positions = np.flatnonzero(wide_mask)
    owner = np.searchsorted(starts, positions, side="right") - 1
    begins = np.flatnonzero(np.diff(owner, prepend=-1))
    ends = np.append(begins[1:], len(owner)) - 1
    # Every half-cycle reaches its own height, so each owns at least one top sample.
    first, last = positions[begins] + offset, positions[ends] + offset
    return first[flat].astype(np.int64), last[flat].astype(np.int64)
