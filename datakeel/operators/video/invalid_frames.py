# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect dark, uniform, frozen and severely blurred video intervals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize
from datakeel.operators.media.tools import probe_file
from datakeel.operators.video.frames import decode_frames, intervals, laplacian_variance

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray
    from pydantic import JsonValue

    from datakeel.core.media_models import MediaInterval
    from datakeel.core.models import FileItem


class InvalidFramesParams(Params):
    """Configure signal thresholds at the documented 160 by 90 sample scale."""

    sample_fps: float = Field(default=5.0, ge=1, le=30)
    black_threshold: float = Field(default=16.0, ge=0, le=255)
    solid_std_threshold: float = Field(default=2.0, ge=0, le=128)
    freeze_difference: float = Field(default=0.75, ge=0, le=255)
    freeze_duration_ms: int = Field(default=1000, ge=100)
    blur_variance_threshold: float = Field(default=8.0, ge=0)
    minimum_interval_ms: int = Field(default=200, ge=0)
    remove: bool = False
    invalid_ratio_threshold: float = Field(default=0.99, gt=0, le=1)


def _deviation(frame: NDArray[np.uint8]) -> float:
    return float(np.std(frame))


def _difference(left: NDArray[np.uint8], right: NDArray[np.uint8]) -> float:
    return float(np.mean(np.abs(left.astype(np.float64) - right)))


def _measure(
    frames: NDArray[np.uint8], duration_ms: int, params: InvalidFramesParams
) -> list[MediaInterval]:
    means = np.mean(frames, axis=(1, 2))
    deviations = np.asarray([_deviation(frames[index]) for index in range(len(frames))])
    differences = np.asarray(
        [_difference(frames[index], frames[index + 1]) for index in range(len(frames) - 1)]
    )
    # Each sampled frame receives its most specific defect: a black frame is also uniform
    # and detail-free, and a uniform frame has no detail, so neither is reported again.
    black = means <= params.black_threshold
    uniform = black | (deviations <= params.solid_std_threshold)
    blurred = (laplacian_variance(frames) < params.blur_variance_threshold) & ~uniform
    checks = (
        ("black_frame", black.tolist()),
        ("solid_frame", (uniform & ~black).tolist()),
        ("blurred_frame", blurred.tolist()),
    )
    issues = [
        issue
        for code, flags in checks
        for issue in intervals(
            flags, code, params.sample_fps, duration_ms, params.minimum_interval_ms
        )
    ]
    step_ms = round(1000 / params.sample_fps)
    # A held picture is a freeze only when it still has content; static uniform frames
    # are already reported above.
    held = (differences <= params.freeze_difference) & ~uniform[:-1] & ~uniform[1:]
    frozen = intervals(
        held.tolist(),
        "frozen_frame",
        params.sample_fps,
        duration_ms,
        max(0, params.freeze_duration_ms - step_ms),
    )
    return issues + [
        issue.model_copy(update={"end_ms": min(duration_ms, issue.end_ms + step_ms)})
        for issue in frozen
    ]


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
        issues = _measure(decode_frames(file, params.sample_fps), probe.duration_ms, params)
        invalid_ms = _invalid_duration(issues)
        invalid_ratio = invalid_ms / max(1, probe.duration_ms)
        metrics: dict[str, JsonValue] = {
            "invalid_duration_ms": invalid_ms,
            "invalid_ratio": invalid_ratio,
        }
        marked = annotate(
            file,
            media_probe=probe.model_dump(mode="json"),
            media_issues=[issue.model_dump(mode="json") for issue in issues],
            video_metrics=metrics,
        )
        if not params.remove or invalid_ratio < params.invalid_ratio_threshold:
            output.append(marked)
        all_issues.extend({"file_id": file.id, **issue.model_dump(mode="json")} for issue in issues)
    return summarize(files, output, all_issues)


OPERATOR = Operator("video.invalid_frames", "video", "quality", InvalidFramesParams, execute)
