# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared activity segmentation and typed audio metadata annotation."""

import numpy as np
from numpy.typing import NDArray

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem
from datakeel.operators.audio.models import ActivityResult, AudioMetrics
from datakeel.operators.audio.params import ActivityParams
from datakeel.operators.audio.streaming import SAMPLE_RATE, channel_blocks
from datakeel.operators.base import annotate
from datakeel.operators.media.tools import probe_file


def runs(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Return half-open index spans where a one-dimensional boolean mask is true."""
    edges = np.diff(np.concatenate(([False], mask, [False])).astype(np.int8))
    return list(
        zip(np.flatnonzero(edges == 1).tolist(), np.flatnonzero(edges == -1).tolist(), strict=True)
    )


def activity(samples: NDArray[np.float64], params: ActivityParams) -> ActivityResult:
    """Estimate sound activity using fixed dBFS RMS windows and duration hysteresis.

    This detects energy, including music and noise. It does not classify speech.
    """
    if not samples.size:
        return ActivityResult(duration_ms=0, active=(), silent=())
    frame_size = SAMPLE_RATE * params.frame_ms // 1000
    starts = np.arange(0, samples.size, frame_size)
    energy = np.add.reduceat(np.square(samples), starts)
    sizes = np.minimum(frame_size, samples.size - starts)
    active = np.sqrt(energy / sizes) >= 10 ** (params.threshold_dbfs / 20)
    return _activity_result(active, samples.size, params)


def measure_activity(file: FileItem, params: ActivityParams) -> ActivityResult:
    """Accumulate frame energies across decode boundaries without retaining PCM samples."""
    frame_size = SAMPLE_RATE * params.frame_ms // 1000
    pending = np.empty(0, dtype=np.float64)
    flags: list[NDArray[np.bool_]] = []
    total = 0
    threshold = 10 ** (params.threshold_dbfs / 20)
    for channels in channel_blocks(file):
        total += len(channels)
        samples = np.concatenate((pending, np.sqrt(np.mean(np.square(channels), axis=1))))
        count = samples.size // frame_size
        frames = samples[: count * frame_size].reshape(count, frame_size)
        flags.append(np.sqrt(np.mean(np.square(frames), axis=1)) >= threshold)
        pending = samples[count * frame_size :].copy()
    if pending.size:
        flags.append(np.array([np.sqrt(np.mean(np.square(pending))) >= threshold]))
    active = np.concatenate(flags) if flags else np.empty(0, dtype=np.bool_)
    return _activity_result(active, total, params)


def _activity_result(
    active: NDArray[np.bool_], samples: int, params: ActivityParams
) -> ActivityResult:
    for start, end in runs(~active):
        if (
            start > 0
            and end < active.size
            and (end - start) * params.frame_ms < params.min_silence_ms
        ):
            active[start:end] = True
    for start, end in runs(active):
        if (end - start) * params.frame_ms < params.min_activity_ms:
            active[start:end] = False
    duration_ms = round(samples * 1000 / SAMPLE_RATE)
    return ActivityResult(
        duration_ms=duration_ms,
        active=_intervals(active, params.frame_ms, duration_ms, "audio_activity"),
        silent=_intervals(~active, params.frame_ms, duration_ms, "audio_silence"),
    )


def _intervals(
    mask: NDArray[np.bool_], frame_ms: int, duration_ms: int, code: str
) -> tuple[MediaInterval, ...]:
    return tuple(
        MediaInterval(code=code, start_ms=start * frame_ms, end_ms=min(end * frame_ms, duration_ms))
        for start, end in runs(mask)
    )


def activity_metrics(result: ActivityResult) -> AudioMetrics:
    """Convert activity spans into quality measurements without claiming speech detection."""
    active_ms = sum(interval.end_ms - interval.start_ms for interval in result.active)
    ratio = active_ms / result.duration_ms if result.duration_ms else 0.0
    return AudioMetrics(
        vad_method="energy_activity_estimate_not_speech_recognition",
        vad_intervals=result.active,
        silence_intervals=result.silent,
        active_ratio=round(ratio, 6),
        silence_ratio=round(1 - ratio, 6),
    )


def annotate_audio(
    file: FileItem, metrics: AudioMetrics, issues: tuple[MediaInterval, ...] = ()
) -> FileItem:
    """Accumulate typed measurements and replace only matching current issue codes."""
    existing = AudioMetrics.model_validate(file.metadata.get("audio_metrics", {}))
    combined = AudioMetrics.model_validate(
        {**existing.model_dump(exclude_none=True), **metrics.model_dump(exclude_unset=True)}
    )
    codes = {issue.code for issue in issues}
    if metrics.silence_ratio is not None:
        codes.add("audio_silence")
    if metrics.clipping_ratio is not None:
        codes.add("audio_clipping")
    if metrics.loudness_measurable is not None:
        codes.add("audio_loudness")
    if metrics.fingerprint_method is not None:
        codes.add("audio_duplicate")
    previous = [
        MediaInterval.model_validate(value) for value in file.metadata.get("media_issues", [])
    ]
    intervals = [issue for issue in previous if issue.code not in codes] + list(issues)
    return annotate(
        file,
        media_probe=probe_file(file).model_dump(mode="json"),
        audio_metrics=combined.model_dump(mode="json", exclude_none=True),
        media_issues=[issue.model_dump(mode="json") for issue in intervals],
    )
