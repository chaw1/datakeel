# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode decoded pixel data into a selected portable raster format."""

from functools import partial
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import ConvertParams, Operator, OperatorResult, summarize
from datakeel.operators.image.helpers import decode, image_artifact
from datakeel.operators.image.parallel import map_images


def _convert(file: FileItem, output_dir: Path, params: ConvertParams) -> FileItem:
    image = decode(file)
    return image_artifact(file, output_dir, image, params.format, params.quality)


def execute(files: list[FileItem], output_dir: Path, params: ConvertParams) -> OperatorResult:
    """Encode decoded pixel data into a selected portable raster format."""
    output = map_images(files, partial(_convert, output_dir=output_dir, params=params))
    return summarize(files, output)


OPERATOR = Operator("image.convert", "image", "transform", ConvertParams, execute)
