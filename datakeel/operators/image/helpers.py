# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded image IO and artifact metadata tied to the current pixel content."""

from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps
from pydantic import JsonValue

from datakeel.core.models import FileItem
from datakeel.operators.base import artifact
from datakeel.operators.image.limits import (
    MAX_IMAGE_BYTES,
    ImageResourceLimit,
    validate_dimensions,
)

_EIGHT_BITS = 8
_SIXTEEN_BITS = 16
_SIXTEEN_BIT_STEP = 65535 / 255


@contextmanager
def open_image(file: FileItem) -> Generator[Image.Image]:
    """Decode a bounded image and release its resources after use."""
    path = Path(file.path)
    if path.stat().st_size > MAX_IMAGE_BYTES:
        msg = f"Encoded image exceeds {MAX_IMAGE_BYTES} bytes"
        raise ImageResourceLimit(msg)
    with Image.open(path) as image:
        validate_dimensions(*image.size)
        image.load()
        yield image


def decode_with_depth(file: FileItem) -> tuple[NDArray[np.uint8], int]:
    """Decode oriented pixels to 8-bit levels and return the decoded bits per sample.

    Pillow keeps 16-bit grayscale in integer modes, and converting those to
    RGB clips every level above 255, so a normal 16-bit image would turn
    white. Such samples are rescaled by their bit depth instead.
    """
    with open_image(file) as image:
        oriented = ImageOps.exif_transpose(image)
        if oriented.mode.startswith("I"):
            levels = np.asarray(oriented, dtype=np.float64) / _SIXTEEN_BIT_STEP
            gray = np.clip(np.round(levels), 0, 255).astype(np.uint8)
            return np.repeat(gray[..., None], 3, axis=2), _SIXTEEN_BITS
        mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
        return np.array(oriented.convert(mode)), _EIGHT_BITS


def decode(file: FileItem) -> NDArray[np.uint8]:
    """Decode oriented image pixels into an 8-bit NumPy array."""
    return decode_with_depth(file)[0]


def encode(image: NDArray[np.uint8], extension: str, quality: int = 90) -> bytes:
    """Encode pixel content to a supported image format."""
    validate_dimensions(image.shape[1], image.shape[0])
    raster = Image.fromarray(image)
    formats = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}
    if extension == "jpg" and raster.mode != "RGB":
        raster = raster.convert("RGB")
    buffer = BytesIO()
    options = {"quality": quality} if extension in {"jpg", "webp"} else {}
    raster.save(buffer, format=formats[extension], **options)
    return buffer.getvalue()


def resize(image: NDArray[np.uint8], dimensions: tuple[int, int]) -> NDArray[np.uint8]:
    """Resize pixels within the declared resource bounds."""
    validate_dimensions(*dimensions)
    return np.array(Image.fromarray(image).resize(dimensions, Image.Resampling.LANCZOS))


def image_artifact(
    file: FileItem,
    output_dir: Path,
    image: NDArray[np.uint8],
    extension: str,
    quality: int = 90,
    **metadata: JsonValue,
) -> FileItem:
    """Create an image artifact with fresh dimension metadata."""
    height, width = image.shape[:2]
    return artifact(
        file,
        output_dir,
        encode(image, extension, quality),
        extension,
        width=width,
        height=height,
        image_quality={"width": width, "height": height},
        **metadata,
    )
