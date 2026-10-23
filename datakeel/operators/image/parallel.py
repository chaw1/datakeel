# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run small image transformations concurrently without multiplying large rasters."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from datakeel.core.models import FileItem
from datakeel.operators.image.limits import MAX_IMAGE_BYTES

# Four small rasters together remain below one supported 16-million-pixel image.
MAX_PARALLEL_PIXELS = 1_000_000
MAX_IMAGE_WORKERS = 4


def _small_image(file: FileItem) -> bool:
    try:
        path = Path(file.path)
        if path.stat().st_size > MAX_IMAGE_BYTES:
            return False
        with Image.open(path) as image:
            return image.width * image.height <= MAX_PARALLEL_PIXELS
    except (OSError, ValueError, Image.DecompressionBombError):
        # Let the original serial decoder report errors in source order.
        return False


def map_images(
    files: list[FileItem], transform: Callable[[FileItem], FileItem], output_pixels: int = 0
) -> list[FileItem]:
    """Preserve input order and serialize batches containing large inputs or outputs."""
    if (
        len(files) <= 1
        or output_pixels > MAX_PARALLEL_PIXELS
        or not all(_small_image(file) for file in files)
    ):
        return [transform(file) for file in files]
    with ThreadPoolExecutor(
        max_workers=min(MAX_IMAGE_WORKERS, len(files)), thread_name_prefix="image"
    ) as pool:
        return list(pool.map(transform, files))
