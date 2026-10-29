# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Global clipping references and bounded windows with exact plateau carry state."""

from collections.abc import Iterator

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.audio.common import runs
from datakeel.operators.audio.flat_tops import (
    flat_tops,
    histogram_reference,
    peak_histogram,
    smoothing_width,
)
from datakeel.operators.audio.params import ClippingParams
from datakeel.operators.audio.streaming import BLOCK_SAMPLES, AudioBuffer

_FLAT = 2 / 32768


def _references(decoded: AudioBuffer) -> list[float]:
    width = smoothing_width(decoded.sample_rate)
    kernel = np.full(width, 1 / width, dtype=np.float32)
    histograms: list[NDArray[np.int64]] = []
    for start, block in decoded.blocks():
        begin = max(0, start - width)
        expanded = decoded.read(begin, start + len(block) + width).astype(np.float32)
        for channel in range(decoded.channels):
            smooth = np.convolve(expanded[:, channel], kernel, mode="same")
            histogram = peak_histogram(smooth[start - begin : start - begin + len(block)])
            if len(histograms) <= channel:
                histograms.append(histogram)
            else:
                histograms[channel] += histogram
    return [histogram_reference(histogram) for histogram in histograms]


def _plateaus(
    decoded: AudioBuffer, channel: int, params: ClippingParams
) -> Iterator[tuple[int, int]]:
    start: int | None = None
    minimum, maximum = float("inf"), float("-inf")
    for offset, block in decoded.blocks():
        signal = block[:, channel].astype(np.float32)
        for left, right in runs(np.abs(signal) >= params.threshold):
            if start is not None and left:
                yield from _plateau_interval(start, offset, minimum, maximum, params)
                start = None
            if start is None:
                start, minimum, maximum = offset + left, float("inf"), float("-inf")
            minimum = min(minimum, float(signal[left:right].min()))
            maximum = max(maximum, float(signal[left:right].max()))
            if right < len(signal):
                yield from _plateau_interval(start, offset + right, minimum, maximum, params)
                start = None
        if start is not None and abs(float(signal[-1])) < params.threshold:
            yield from _plateau_interval(start, offset, minimum, maximum, params)
            start = None
    yield from _plateau_interval(start, decoded.samples, minimum, maximum, params)


def _plateau_interval(
    start: int | None, stop: int, minimum: float, maximum: float, params: ClippingParams
) -> tuple[tuple[int, int], ...]:
    if (
        start is not None
        and stop - start >= params.min_consecutive_samples
        and (maximum - minimum <= _FLAT)
    ):
        return ((start, stop),)
    return ()


def _saturated(
    signal: NDArray[np.float32], params: ClippingParams, window: int
) -> NDArray[np.bool_]:
    near = np.abs(signal) >= params.saturation_level
    count = near.size // window
    flagged = np.zeros(signal.shape, dtype=np.bool_)
    if count:
        occupancy = near[: count * window].reshape(count, window).mean(axis=1)
        dwelling = np.repeat(occupancy >= params.saturation_occupancy, window)
        flagged[: count * window] = dwelling & near[: count * window]
    return flagged


def clipping_blocks(
    decoded: AudioBuffer, params: ClippingParams
) -> Iterator[tuple[int, NDArray[np.bool_]]]:
    """Yield union masks with globally aligned windows and carried plateau decisions."""
    if not decoded.samples:
        return
    references = _references(decoded)
    plateaus = [_plateaus(decoded, channel, params) for channel in range(decoded.channels)]
    pending = [next(intervals, None) for intervals in plateaus]
    window = max(1, decoded.sample_rate * params.window_ms // 1000)
    size = max(1, BLOCK_SAMPLES // window) * window
    halo = 2 * window
    for start in range(0, decoded.samples, size):
        stop = min(decoded.samples, start + size)
        begin = max(0, start - halo)
        expanded = decoded.read(begin, stop + halo).astype(np.float32)
        flagged = np.zeros((stop - start, decoded.channels), dtype=np.bool_)
        for channel in range(decoded.channels):
            signal = expanded[:, channel]
            local = _saturated(signal, params, window) | flat_tops(
                signal, decoded.sample_rate, params.window_ms, reference=references[channel]
            )
            flagged[:, channel] = local[start - begin : stop - begin]
            interval = pending[channel]
            while interval is not None and interval[0] < stop:
                left, right = interval
                flagged[max(start, left) - start : min(stop, right) - start, channel] = True
                if right > stop:
                    break
                interval = next(plateaus[channel], None)
            pending[channel] = interval
        yield start, flagged
