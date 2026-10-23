# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode decoded pixel data into a selected portable raster format."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import ConvertParams, Operator, OperatorResult, summarize
from datakeel.operators.image.helpers import decode, image_artifact


def execute(files: list[FileItem], output_dir: Path, params: ConvertParams) -> OperatorResult:
    """Encode decoded pixel data into a selected portable raster format."""
    output: list[FileItem] = []
    for file in files:
        image = decode(file)
        output.append(image_artifact(file, output_dir, image, params.format, params.quality))
    return summarize(files, output)


OPERATOR = Operator("image.convert", "image", "transform", ConvertParams, execute)
