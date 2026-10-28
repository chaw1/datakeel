# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create small previews without upscaling smaller inputs."""

from functools import partial
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, ThumbnailParams
from datakeel.operators.image.batch import guarded, summarize_batch
from datakeel.operators.image.helpers import decode, image_artifact, resize
from datakeel.operators.image.parallel import map_images


def _thumbnail(file: FileItem, output_dir: Path, params: ThumbnailParams) -> FileItem:
    image = decode(file)
    height, width = image.shape[:2]
    ratio = min(1.0, params.size / width, params.size / height)
    dimensions = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    preview = resize(image, dimensions)
    return image_artifact(file, output_dir, preview, "png", usage_role="preview")


def execute(files: list[FileItem], output_dir: Path, params: ThumbnailParams) -> OperatorResult:
    """Create small previews without upscaling smaller inputs."""
    output = map_images(
        files,
        guarded("image.thumbnail", partial(_thumbnail, output_dir=output_dir, params=params)),
        params.size * params.size,
    )
    return summarize_batch(files, output)


OPERATOR = Operator("image.thumbnail", "image", "preview", ThumbnailParams, execute)
