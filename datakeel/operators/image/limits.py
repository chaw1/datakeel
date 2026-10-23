# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image memory bounds shared by parameter validation and header inspection."""

from datakeel.core.errors import ValidationError

MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


class ImageResourceLimitError(ValidationError):
    """An image exceeds the local worker's documented processing envelope."""


def validate_dimensions(width: int, height: int) -> None:
    """Reject unsafe decoded-image dimensions."""
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        msg = f"Image dimensions must contain 1 to {MAX_IMAGE_PIXELS} pixels"
        raise ImageResourceLimitError(msg)


# Preserve the original public exception import used by operator clients.
ImageResourceLimit = ImageResourceLimitError
