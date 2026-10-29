# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare recordings by MFCC spectral shape and the time course of its fluctuations.

Independent recordings of the same kind of sound (two noise takes, two rooms) share a
spectral shape but fluctuate independently, while a copy keeps its fluctuations through
gain changes and lossy re-encoding. Steady tones have no fluctuation, so their spectral
shape alone decides.
"""

from itertools import pairwise
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.audio.common import SAMPLE_RATE
from datakeel.operators.audio.models import Fingerprint
from datakeel.operators.audio.params import DedupParams

_FFT_SIZE = 512
_FRAME_SIZE = 400
_HOP_SIZE = 160
_BLOCK_FRAMES = 5
_MEL_FILTERS = 26
_COEFFICIENTS = 13
_TIME_BINS = 64
# Block MFCC fluctuation (RMS, natural-log units) separating steady tones from varying sound.
_STEADY_FLUCTUATION = 0.05
_BLOCK_MS = _BLOCK_FRAMES * _HOP_SIZE * 1000 // SAMPLE_RATE
_MIN_SCALE = 1e-12


class Signature(NamedTuple):
    """Hold the block MFCC sequence of one recording and its source duration."""

    duration_ms: int
    blocks: NDArray[np.float64]


def _mel_filters() -> NDArray[np.float64]:
    mel_max = float(2595 * np.log10(1 + SAMPLE_RATE / 2 / 700))
    mel_points = np.arange(_MEL_FILTERS + 2, dtype=np.float64) * mel_max / (_MEL_FILTERS + 1)
    frequencies = 700 * (np.power(10.0, mel_points / 2595) - 1)
    bins = np.floor((_FFT_SIZE + 1) * frequencies / SAMPLE_RATE).astype(np.int64)
    filters = np.zeros((_MEL_FILTERS, _FFT_SIZE // 2 + 1), dtype=np.float64)
    positions = np.arange(_FFT_SIZE // 2 + 1)
    for index in range(_MEL_FILTERS):
        left, center, right = bins[index : index + 3]
        filters[index] = np.maximum(
            0,
            np.minimum(
                (positions - left) / max(center - left, 1),
                (right - positions) / max(right - center, 1),
            ),
        )
    return filters


def signature(samples: NDArray[np.float64]) -> Signature:
    """Return 50 ms block MFCCs, excluding the gain-dependent zeroth coefficient."""
    duration_ms = round(samples.size * 1000 / SAMPLE_RATE)
    if samples.size < _FRAME_SIZE:
        samples = np.pad(samples, (0, _FRAME_SIZE - samples.size))
    emphasized = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
    frames = np.lib.stride_tricks.sliding_window_view(emphasized, _FRAME_SIZE)[::_HOP_SIZE]
    spectrum = np.abs(np.fft.rfft(frames * np.hamming(_FRAME_SIZE), n=_FFT_SIZE)) ** 2
    mel_power = spectrum @ _mel_filters().T
    # A relative 60 dB floor suppresses PCM quantization noise after gain changes.
    floor = max(float(mel_power.max()) * 1e-6, 1e-30)
    basis = np.cos(
        np.pi
        / _MEL_FILTERS
        * (np.arange(_MEL_FILTERS) + 0.5)[None, :]
        * np.arange(1, _COEFFICIENTS + 1)[:, None]
    ) * np.sqrt(2 / _MEL_FILTERS)
    coefficients = np.log(np.maximum(mel_power, floor)) @ basis.T
    count = len(coefficients) // _BLOCK_FRAMES
    if count == 0:
        return Signature(duration_ms, coefficients.mean(axis=0, keepdims=True))
    blocks = coefficients[: count * _BLOCK_FRAMES].reshape(count, _BLOCK_FRAMES, _COEFFICIENTS)
    return Signature(duration_ms, blocks.mean(axis=1))


def fingerprint(value: Signature) -> Fingerprint:
    """Summarize the block sequence as 64 ordered MFCC bins for stored metadata."""
    edges = np.linspace(0, len(value.blocks), _TIME_BINS + 1)
    bins = [
        value.blocks[int(start) : max(int(start) + 1, int(stop))].mean(axis=0)
        for start, stop in pairwise(edges)
    ]
    values = tuple(round(float(number), 6) for number in np.concatenate(bins))
    return Fingerprint(duration_ms=value.duration_ms, coefficients=values)


def shape_similarity(first: Signature, second: Signature) -> float:
    """Compare average spectral shape with a bounded relative Euclidean distance."""
    left, right = first.blocks.mean(axis=0), second.blocks.mean(axis=0)
    scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1e-9)
    return max(0.0, 1 - float(np.linalg.norm(left - right)) / scale)


def fluctuation(value: Signature) -> float:
    """Measure how much the block MFCCs vary over time around their mean."""
    return float(np.sqrt(np.mean(np.square(value.blocks - value.blocks.mean(axis=0)))))


def fluctuation_correlation(first: Signature, second: Signature, max_lag_ms: int) -> float:
    """Return the best Pearson correlation of MFCC fluctuations within the lag window."""
    best = -1.0
    lag_blocks = max_lag_ms // _BLOCK_MS
    for lag in range(-lag_blocks, lag_blocks + 1):
        left = first.blocks[max(0, lag) :]
        right = second.blocks[max(0, -lag) :]
        count = min(len(left), len(right))
        if count < 2:  # noqa: PLR2004  # A correlation needs at least two blocks.
            continue
        left = left[:count] - left[:count].mean(axis=0)
        right = right[:count] - right[:count].mean(axis=0)
        scale = float(np.linalg.norm(left) * np.linalg.norm(right))
        if scale > _MIN_SCALE:
            best = max(best, float(np.sum(left * right)) / scale)
    return best


def is_duplicate(first: Signature, second: Signature, params: DedupParams) -> bool:
    """Decide whether two recordings carry the same sound, ignoring gain and codec loss."""
    longest = max(first.duration_ms, second.duration_ms, 1)
    if abs(first.duration_ms - second.duration_ms) > longest * params.duration_tolerance:
        return False
    steady = [fluctuation(value) < _STEADY_FLUCTUATION for value in (first, second)]
    if all(steady):
        return shape_similarity(first, second) >= params.stationary_threshold
    if any(steady):
        return False
    return (
        shape_similarity(first, second) >= params.shape_threshold
        and fluctuation_correlation(first, second, params.max_lag_ms)
        >= params.correlation_threshold
    )
