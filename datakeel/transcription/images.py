# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize image geometry and remove metadata before any OCR or outbound request."""

import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.core.transcription_models import ImageInput


def normalize_image(content: bytes) -> ImageInput:
    """Apply EXIF rotation once, then encode pixels without EXIF, GPS or text metadata."""
    try:
        with Image.open(BytesIO(content)) as source:
            corrected = ImageOps.exif_transpose(source)
            if "A" in corrected.getbands() or "transparency" in corrected.info:
                rgba = corrected.convert("RGBA")
                white = Image.new("RGBA", rgba.size, "white")
                corrected = Image.alpha_composite(white, rgba)
            corrected = corrected.convert("RGB")
            clean = Image.frombytes("RGB", corrected.size, corrected.tobytes())
            output = BytesIO()
            clean.save(output, format="PNG")
            return ImageInput(
                image_hash=hashlib.sha256(content).hexdigest(),
                png=output.getvalue(),
                width=clean.width,
                height=clean.height,
            )
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        message = "Image could not be decoded"
        raise TranscriptionUnavailableError(message, reason="image_decode_error") from error
