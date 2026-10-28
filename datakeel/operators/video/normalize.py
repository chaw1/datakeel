# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize video encoding, dimensions and frame rate."""

from pathlib import Path

from pydantic import Field, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize
from datakeel.operators.media.tools import media_artifact
from datakeel.operators.video.render import render


class NormalizeParams(Params):
    """Declare an MPEG-4/AAC MP4 with square pixels and letterboxed content."""

    width: int = Field(default=640, ge=2, le=4096)
    height: int = Field(default=360, ge=2, le=4096)
    frame_rate: float = Field(default=30.0, ge=1, le=120)

    @model_validator(mode="after")
    def even_dimensions(self) -> "NormalizeParams":
        """Require chroma-compatible output dimensions."""
        if self.width % 2 or self.height % 2:
            msg = "Video output width and height must be even"
            raise ValidationError(msg)
        return self


def execute(files: list[FileItem], output_dir: Path, params: NormalizeParams) -> OperatorResult:
    """Encode normalized files while retaining immutable originals."""
    filters = (
        f"fps={params.frame_rate},scale={params.width}:{params.height}:"
        "force_original_aspect_ratio=decrease:force_divisible_by=2,"
        f"pad={params.width}:{params.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
    )
    output = [
        _carry_measurements(
            file,
            media_artifact(
                file, output_dir, render(file, filters), "mp4", "video.normalize", params
            ),
        )
        for file in files
    ]
    return summarize(files, output)


def _carry_measurements(source: FileItem, normalized: FileItem) -> FileItem:
    """Keep measured issue intervals: normalization preserves the source timeline."""
    carried = {
        key: source.metadata[key]
        for key in ("media_issues", "video_metrics")
        if key in source.metadata
    }
    return annotate(normalized, **carried)


OPERATOR = Operator("video.normalize", "video", "normalization", NormalizeParams, execute)
