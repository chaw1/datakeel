# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize image geometry and remove metadata before any OCR or outbound request."""

import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from datakeel.core.errors import ValidationError
from datakeel.core.transcription_models import ImageInput


def normalize_image(content: bytes) -> ImageInput:
    """Apply EXIF rotation once, then encode pixels without EXIF, GPS or text metadata."""
    try:
        with Image.open(BytesIO(content)) as source:
            corrected = ImageOps.exif_transpose(source).convert("RGB")
            clean = Image.frombytes("RGB", corrected.size, corrected.tobytes())
            output = BytesIO()
            clean.save(output, format="PNG")
            return ImageInput(
                image_hash=hashlib.sha256(content).hexdigest(),
                png=output.getvalue(),
                width=clean.width,
                height=clean.height,
            )
    except (OSError, ValueError, UnidentifiedImageError) as error:
        message = "Image could not be decoded"
        raise ValidationError(message) from error
