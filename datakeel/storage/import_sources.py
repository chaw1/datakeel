# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read image headers before imported files are stored."""

import warnings
from pathlib import Path

from PIL import Image
from pydantic import JsonValue


def image_dimensions(path: Path) -> dict[str, JsonValue]:
    """Read width and height from the image header; record both as unknown when unreadable."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = image.size
    except (OSError, ValueError, Image.DecompressionBombError):
        return {"width": None, "height": None}
    return {"width": width, "height": height}
