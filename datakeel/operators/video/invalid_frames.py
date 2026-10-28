# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect dark, uniform, frozen and severely blurred video intervals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from datakeel.core.media_models import MediaInterval
from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize
from datakeel.operators.media.tools import probe_file
from datakeel.operators.video.analysis import analyse
from datakeel.operators.video.frames import intervals
from datakeel.operators.video.freeze import frozen_runs

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.core.models import FileItem
    from datakeel.operators.video.analysis import VideoAnalysis

# Issue codes this operator measures; issues other operators recorded are kept.
_MEASURED = frozenset({"black_frame", "solid_frame", "blurred_frame", "frozen_frame"})


class InvalidFramesParams(Params):
    """Configure signal thresholds at the documented 160 by 90 analysis scale.

    ``sample_fps`` is the maximum analysis rate: slower video is examined frame by
    frame, so interval boundaries are exact to one frame.
    """

    sample_fps: float = Field(default=30.0, ge=1, le=60)
    black_threshold: float = Field(default=16.0, ge=0, le=255)
    solid_std_threshold: float = Field(default=2.0, ge=0, le=128)
    freeze_difference: float = Field(default=0.75, ge=0, le=255)
    freeze_local_difference: float = Field(default=2.0, ge=0, le=255)
    freeze_locality: float = Field(default=10.0, ge=1, le=1000)
    freeze_noise_ratio: float = Field(default=0.5, ge=0, le=10)
    freeze_duration_ms: int = Field(default=1200, ge=100)
    blur_variance_threshold: float = Field(default=8.0, ge=0)
    minimum_interval_ms: int = Field(default=200, ge=0)
    remove: bool = False
    invalid_ratio_threshold: float = Field(default=0.99, gt=0, le=1)


def _measure(analysis: VideoAnalysis, params: InvalidFramesParams) -> list[MediaInterval]:
    # Each frame receives its most specific defect: a black frame is also uniform and
    # detail-free, and a uniform frame has no detail, so neither is reported again.
    black = analysis.mean <= params.black_threshold
    uniform = black | (analysis.deviation <= params.solid_std_threshold)
    blurred = (analysis.detail < params.blur_variance_threshold) & ~uniform
    checks = (
        ("black_frame", black.tolist()),
        ("solid_frame", (uniform & ~black).tolist()),
        ("blurred_frame", blurred.tolist()),
    )
    duration_ms = analysis.duration_ms
    issues = [
        issue
        for code, flags in checks
        for issue in intervals(flags, code, analysis.rate, duration_ms, params.minimum_interval_ms)
    ]
    for first, last in frozen_runs(analysis, uniform, params):
        start_ms = round(first * analysis.frame_ms)
        end_ms = min(duration_ms, round((last + 1) * analysis.frame_ms))
        if end_ms - start_ms >= params.freeze_duration_ms:
            issues.append(MediaInterval(code="frozen_frame", start_ms=start_ms, end_ms=end_ms))
    return issues


def _invalid_duration(issues: list[MediaInterval]) -> int:
    ranges = sorted((issue.start_ms, issue.end_ms) for issue in issues)
    total = end = 0
    for start_ms, end_ms in ranges:
        total += max(0, end_ms - max(start_ms, end))
        end = max(end, end_ms)
    return total


def execute(
    files: list[FileItem], _output_dir: Path, params: InvalidFramesParams
) -> OperatorResult:
    """Annotate issue intervals and optionally remove wholly invalid recordings."""
    output: list[FileItem] = []
    all_issues: list[dict[str, object]] = []
    for file in files:
        probe = probe_file(file)
        issues = _measure(analyse(file, params.sample_fps), params)
        invalid_ms = _invalid_duration(issues)
        invalid_ratio = invalid_ms / max(1, probe.duration_ms)
        metrics: dict[str, JsonValue] = {
            "invalid_duration_ms": invalid_ms,
            "invalid_ratio": invalid_ratio,
        }
        kept = [
            value
            for value in file.metadata.get("media_issues", [])
            if value.get("code") not in _MEASURED
        ]
        marked = annotate(
            file,
            media_probe=probe.model_dump(mode="json"),
            media_issues=[*kept, *(issue.model_dump(mode="json") for issue in issues)],
            video_metrics=metrics,
        )
        if not params.remove or invalid_ratio < params.invalid_ratio_threshold:
            output.append(marked)
        all_issues.extend({"file_id": file.id, **issue.model_dump(mode="json")} for issue in issues)
    return summarize(files, output, all_issues)


OPERATOR = Operator("video.invalid_frames", "video", "quality", InvalidFramesParams, execute)
