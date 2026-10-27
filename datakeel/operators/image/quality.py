# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure and explain image usability with five deterministic quality signals."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from datakeel.core.models import FileItem
from datakeel.operators.base import (
    ImageQualityParams,
    Operator,
    OperatorResult,
    annotate,
    summarize,
)
from datakeel.operators.image.helpers import decode
from datakeel.operators.image.quality_scores import ImageQualityChecks, evaluate
from datakeel.operators.image.quality_signals import ImageSignals, measure

if TYPE_CHECKING:
    from pydantic import JsonValue

_DIMENSIONS = ("blur", "exposure", "noise", "resolution", "solid_color")
_LEGACY_CODES = {"blurry", "brightness", "low_resolution"}


class ImageQualityMeasurement(ImageSignals):
    """Retain legacy fields and typed scores suitable for quality reports and cleanup."""

    checks: ImageQualityChecks
    scores: dict[str, float]
    score: float
    overall_score: float
    failed: bool
    reasons: list[str]
    issues: list[str]


def _quality(file: FileItem, params: ImageQualityParams) -> ImageQualityMeasurement:
    signals = measure(decode(file), params.analysis_size)
    checks = evaluate(signals, params)
    values = checks.values()
    # Basic usability requires all five checks; an isolated severe defect must
    # remain selectable through the existing low-quality cleanup threshold.
    overall = min(check.score for check in values)
    return ImageQualityMeasurement(
        **signals.model_dump(),
        checks=checks,
        scores={key: check.score for key, check in zip(_DIMENSIONS, values, strict=True)},
        score=overall,
        overall_score=overall,
        failed=any(check.failed for check in values),
        reasons=[check.reason for check in values if check.failed],
        issues=[check.code for check in values if check.failed and check.code in _LEGACY_CODES],
    )


def execute(files: list[FileItem], _output_dir: Path, params: ImageQualityParams) -> OperatorResult:
    """Annotate oriented images with scores, threshold failures and measured explanations."""
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    measurements: dict[str, JsonValue] = {}
    for file in files:
        quality = _quality(file, params)
        serialized = cast("dict[str, JsonValue]", quality.model_dump(mode="json"))
        measurements[file.id] = serialized
        output.append(
            annotate(
                file,
                width=quality.width,
                height=quality.height,
                image_quality=serialized,
            )
        )
        issues.extend(
            {
                "file_id": file.id,
                "code": check.code,
                "severity": "warning",
                "score": check.score,
                "reason": check.reason,
            }
            for check in quality.checks.values()
            if check.failed
        )
    result = summarize(files, output, issues)
    result.quality["measurements"] = measurements
    return result


OPERATOR = Operator("image.quality", "image", "quality", ImageQualityParams, execute)
