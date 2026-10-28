# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resize images within requested dimensions, retaining aspect ratio by default."""

from functools import partial
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, ResizeParams
from datakeel.operators.image.batch import guarded, summarize_batch
from datakeel.operators.image.helpers import decode, image_artifact, resize
from datakeel.operators.image.parallel import map_images


def _resize(file: FileItem, output_dir: Path, params: ResizeParams) -> FileItem:
    image = decode(file)
    height, width = image.shape[:2]
    dimensions = (params.width, params.height)
    if params.preserve_aspect:
        ratio = min(params.width / width, params.height / height)
        dimensions = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    resized = resize(image, dimensions)
    return image_artifact(file, output_dir, resized, "png")


def execute(files: list[FileItem], output_dir: Path, params: ResizeParams) -> OperatorResult:
    """Resize images within requested dimensions, retaining aspect ratio by default."""
    output = map_images(
        files,
        guarded("image.resize", partial(_resize, output_dir=output_dir, params=params)),
        params.width * params.height,
    )
    return summarize_batch(files, output)


OPERATOR = Operator("image.resize", "image", "transform", ResizeParams, execute)
