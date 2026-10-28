# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure full-scale plateaus independently in every original audio channel."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem
from datakeel.operators.audio.common import annotate_audio, runs
from datakeel.operators.audio.models import AudioMetrics
from datakeel.operators.audio.params import ClippingParams
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.media.tools import input_path, media_timeout, probe_file, run_tool

# Largest variation (two 16-bit steps) within a run that is still a flat plateau.
_FLAT = 2 / 32768


def _plateaus(channel: NDArray[np.float32], params: ClippingParams) -> NDArray[np.bool_]:
    """Flag runs held flat at full scale, as converters and integer PCM clip.

    A lossy decoder's overshoot can exceed full scale for a few samples of an
    unclipped waveform, but those samples still move; a clipped run does not.
    """
    flagged = np.zeros(channel.shape, dtype=np.bool_)
    for start, end in runs(np.abs(channel) >= params.threshold):
        if end - start >= params.min_consecutive_samples and (
            float(np.ptp(channel[start:end])) <= _FLAT
        ):
            flagged[start:end] = True
    return flagged


def _saturated(
    channel: NDArray[np.float32], params: ClippingParams, sample_rate: int
) -> NDArray[np.bool_]:
    """Flag windows that dwell near full scale, as lossy-coded clipped plateaus do.

    Unclipped waveforms rarely stay near full scale: even a full-scale sine spends
    about 35% of each cycle above 0.85, while a clipped one stays there most of the time.
    """
    near = np.abs(channel) >= params.saturation_level
    window = max(1, sample_rate * params.window_ms // 1000)
    count = near.size // window
    flagged = np.zeros(channel.shape, dtype=np.bool_)
    if count:
        occupancy = near[: count * window].reshape(count, window).mean(axis=1)
        dwelling = np.repeat(occupancy >= params.saturation_occupancy, window)
        flagged[: count * window] = dwelling & near[: count * window]
    return flagged


def _measure(
    file: FileItem, params: ClippingParams
) -> tuple[AudioMetrics, tuple[MediaInterval, ...]]:
    probe = probe_file(file)
    channels = probe.channels or 1
    sample_rate = probe.sample_rate or 16000
    raw = run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            input_path(file),
            "-map",
            "0:a:0",
            "-c:a",
            "pcm_f32le",
            "-f",
            "f32le",
            "pipe:1",
        ],
        timeout=media_timeout(probe.duration_ms),
    )
    # Single precision halves the memory of long recordings; thresholds need no more.
    samples = np.frombuffer(raw, dtype="<f4").reshape(-1, channels)
    clipped = np.zeros(samples.shape, dtype=np.bool_)
    for channel in range(channels):
        clipped[:, channel] = _plateaus(samples[:, channel], params) | _saturated(
            samples[:, channel], params, sample_rate
        )
    count = int(np.count_nonzero(clipped))
    metrics = AudioMetrics(
        clipped_samples=count,
        clipping_ratio=round(count / samples.size, 8) if samples.size else 0.0,
    )
    return metrics, _clipping_intervals(np.any(clipped, axis=1), sample_rate, params)


def _clipping_intervals(
    mask: NDArray[np.bool_], sample_rate: int, params: ClippingParams
) -> tuple[MediaInterval, ...]:
    """Merge plateaus closer than ``merge_gap_ms`` so one distorted passage is one issue."""
    gap = sample_rate * params.merge_gap_ms // 1000
    merged: list[list[int]] = []
    for start, end in runs(mask):
        if merged and start - merged[-1][1] <= gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return tuple(
        MediaInterval(
            code="audio_clipping",
            start_ms=start * 1000 // sample_rate,
            end_ms=max(
                start * 1000 // sample_rate + 1, (end * 1000 + sample_rate - 1) // sample_rate
            ),
        )
        for start, end in merged
    )


def execute(files: list[FileItem], _output_dir: Path, params: ClippingParams) -> OperatorResult:
    """Annotate clipping ratio and source intervals without stereo phase cancellation."""
    output: list[FileItem] = []
    for file in files:
        metrics, intervals = _measure(file, params)
        output.append(annotate_audio(file, metrics, intervals))
    return summarize(files, output)


OPERATOR = Operator("audio.clipping", "audio", "quality", ClippingParams, execute)
