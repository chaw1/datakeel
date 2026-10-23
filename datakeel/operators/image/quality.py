# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure image sharpness, brightness and pixel dimensions."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import (
    ImageQualityParams,
    Operator,
    OperatorResult,
    annotate,
    summarize,
)
from datakeel.operators.image.helpers import decode

if TYPE_CHECKING:
    from pydantic import JsonValue


def execute(files: list[FileItem], _output_dir: Path, params: ImageQualityParams) -> OperatorResult:
    """Measure image sharpness, brightness and pixel dimensions."""
    if params.min_brightness > params.max_brightness:
        msg = "min_brightness must not exceed max_brightness"
        raise ValidationError(msg)
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    measurements: dict[str, Any] = {}
    for file in files:
        image = decode(file)
        gray = np.dot(image[..., :3], np.array([0.299, 0.587, 0.114], dtype=np.float32))
        height, width = gray.shape[:2]
        padded = np.pad(gray, 1, mode="edge")
        laplacian = (
            padded[1:-1, :-2] + padded[1:-1, 2:] + padded[:-2, 1:-1] + padded[2:, 1:-1] - 4 * gray
        )
        blur = float(laplacian.var())
        brightness = float(gray.mean())
        problems: list[str] = []
        if blur < params.blur_threshold:
            problems.append("blurry")
        if not params.min_brightness <= brightness <= params.max_brightness:
            problems.append("brightness")
        if min(width, height) < params.min_resolution:
            problems.append("low_resolution")
        quality: dict[str, JsonValue] = {
            "width": width,
            "height": height,
            "blur_variance": round(blur, 3),
            "brightness": round(brightness, 3),
            "issues": list(problems),
        }
        measurements[file.id] = quality
        output.append(annotate(file, width=width, height=height, image_quality=quality))
        issues.extend(
            {"file_id": file.id, "code": code, "severity": "warning"} for code in problems
        )
    result = summarize(files, output, issues)
    result.quality["measurements"] = measurements
    return result


OPERATOR = Operator("image.quality", "image", "quality", ImageQualityParams, execute)
