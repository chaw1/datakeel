# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure clipped passages independently in every original audio channel.

Three kinds of evidence: runs held flat at full scale (PCM), windows dwelling near
full scale (hard clipping of tones, which keeps them there after lossy coding), and
clusters of flat-topped peaks near the track's own peak level (voice and music clipped
before lossy coding, see :mod:`datakeel.operators.audio.flat_tops`).
"""

from pathlib import Path

import numpy as np

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem
from datakeel.operators.audio.clipping_stream import clipping_blocks
from datakeel.operators.audio.common import annotate_audio, runs
from datakeel.operators.audio.models import AudioMetrics
from datakeel.operators.audio.params import ClippingParams
from datakeel.operators.audio.streaming import audio_buffer
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.media.tools import probe_file


def _measure(
    file: FileItem, params: ClippingParams
) -> tuple[AudioMetrics, tuple[MediaInterval, ...]]:
    probe = probe_file(file)
    sample_rate = probe.sample_rate or 16000
    count, total = 0, 0
    merged: list[list[int]] = []
    gap = sample_rate * params.merge_gap_ms // 1000
    with audio_buffer(file, sample_rate) as decoded:
        for offset, clipped in clipping_blocks(decoded, params):
            count += int(np.count_nonzero(clipped))
            total += clipped.size
            for left, right in runs(np.any(clipped, axis=1)):
                start, end = left + offset, right + offset
                if merged and start - merged[-1][1] <= gap:
                    merged[-1][1] = end
                else:
                    merged.append([start, end])
    metrics = AudioMetrics(
        clipped_samples=count,
        clipping_ratio=round(count / total, 8) if total else 0.0,
    )
    return metrics, _clipping_intervals(merged, sample_rate)


def _clipping_intervals(merged: list[list[int]], sample_rate: int) -> tuple[MediaInterval, ...]:
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
