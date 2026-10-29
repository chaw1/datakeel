# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure EBU R128 integrated loudness and optionally normalize with two passes."""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING, cast

from datakeel.core.errors import ExecutionError
from datakeel.core.media_models import MediaInterval
from datakeel.operators.audio.common import annotate_audio
from datakeel.operators.audio.models import AudioMetrics, LoudnessMeasurement
from datakeel.operators.audio.params import LoudnessParams
from datakeel.operators.audio.streaming import stream_artifact
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.media.tools import (
    input_path,
    media_timeout,
    probe_file,
    run_tool_stderr,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.models import FileItem


def _filter(params: LoudnessParams) -> str:
    return (
        f"loudnorm=I={params.target_lufs}:TP={params.true_peak_dbfs}:LRA={params.loudness_range_lu}"
    )


def measure(file: FileItem, params: LoudnessParams) -> LoudnessMeasurement:
    """Run ffmpeg's EBU R128 loudnorm analysis and parse finite measurements."""
    diagnostic = run_tool_stderr(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            input_path(file),
            "-map",
            "0:a:0",
            "-af",
            _filter(params) + ":print_format=json",
            "-f",
            "null",
            "-",
        ],
        timeout=media_timeout(probe_file(file).duration_ms),
    ).decode(errors="replace")
    matches = re.findall(r"\{[^{}]*\}", diagnostic)
    if not matches:
        msg = "ffmpeg did not return EBU R128 loudness measurements"
        raise ExecutionError(msg)
    document = cast("dict[str, str]", json.loads(matches[-1]))
    return LoudnessMeasurement(
        integrated_lufs=_finite(document.get("input_i")),
        loudness_range_lu=_finite(document.get("input_lra")),
        true_peak_dbfs=_finite(document.get("input_tp")),
        threshold_lufs=_finite(document.get("input_thresh")),
    )


def _finite(value: str | None) -> float | None:
    number = float(value) if value is not None else math.nan
    return number if math.isfinite(number) else None


def _normalize(
    file: FileItem, output_dir: Path, params: LoudnessParams, measured: LoudnessMeasurement
) -> FileItem:
    filters = (
        _filter(params)
        + f":measured_I={measured.integrated_lufs}:measured_TP={measured.true_peak_dbfs}"
        + f":measured_LRA={measured.loudness_range_lu}:measured_thresh={measured.threshold_lufs}"
        + ":linear=true"
    )
    probe = probe_file(file)
    return stream_artifact(
        file,
        output_dir,
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            input_path(file),
            "-map",
            "0:a:0",
            "-af",
            filters,
            "-ar",
            str(probe.sample_rate or 48000),
            "-map_metadata",
            "-1",
            "-c:a",
            "pcm_s24le",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            "-f",
            "wav",
            "pipe:1",
        ],
        "audio.loudness",
        params,
        start_ms=0,
        end_ms=probe.duration_ms,
    )


def deviation_lu(integrated_lufs: float, params: LoudnessParams) -> float:
    """Return how far loudness lies outside the acceptable range (0 inside it)."""
    below = params.acceptable_min_lufs - integrated_lufs
    above = integrated_lufs - params.acceptable_max_lufs
    return max(0.0, below, above)


def _annotate(file: FileItem, measured: LoudnessMeasurement, params: LoudnessParams) -> FileItem:
    deviation = (
        deviation_lu(measured.integrated_lufs, params)
        if measured.integrated_lufs is not None
        else None
    )
    metrics = AudioMetrics(
        integrated_lufs=measured.integrated_lufs,
        loudness_range_lu=measured.loudness_range_lu,
        true_peak_dbfs=measured.true_peak_dbfs,
        target_lufs=params.target_lufs,
        acceptable_min_lufs=params.acceptable_min_lufs,
        acceptable_max_lufs=params.acceptable_max_lufs,
        loudness_tolerance_lu=params.loudness_tolerance_lu,
        loudness_deviation_lu=round(deviation, 3) if deviation is not None else None,
        loudness_measurable=measured.integrated_lufs is not None,
    )
    intervals = (
        (MediaInterval(code="audio_loudness", start_ms=0, end_ms=probe_file(file).duration_ms),)
        if deviation is None or deviation > params.loudness_tolerance_lu
        else ()
    )
    return annotate_audio(file, metrics, intervals)


def execute(files: list[FileItem], output_dir: Path, params: LoudnessParams) -> OperatorResult:
    """Measure original or normalized content, leaving unmeasurable silence explicit."""
    output: list[FileItem] = []
    for file in files:
        target = file
        measured = measure(file, params)
        if params.normalize and measured.integrated_lufs is not None:
            target = _normalize(file, output_dir, params, measured)
            measured = measure(target, params)
        output.append(_annotate(target, measured, params))
    return summarize(files, output)


OPERATOR = Operator("audio.loudness", "audio", "quality", LoudnessParams, execute)
