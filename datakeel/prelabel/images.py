# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode exactly the workbench pixels, downscaled and metadata-free, for a provider request."""

import base64
import math
from io import BytesIO
from typing import NamedTuple

from PIL import Image, ImageOps

_MIN_TILES = 4
_MARKER_TOKENS = 2


class SentImage(NamedTuple):
    """One encoded view and the geometry needed to map its coordinates back to the source."""

    data_url: str
    width: int
    height: int
    source_width: int
    source_height: int
    mirrored: bool


def sent_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Shrink to fit ``max_side`` while keeping the aspect ratio; never enlarge."""
    scale = min(1.0, max_side / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def image_tokens(width: int, height: int, patch: int) -> int:
    """Estimate image tokens: one per ``patch``-pixel square tile (min four) plus two markers."""
    tiles = max(_MIN_TILES, math.ceil(width / patch) * math.ceil(height / patch))
    return tiles + _MARKER_TOKENS


def encode_view(image: Image.Image, max_side: int, *, mirrored: bool = False) -> SentImage:
    """Return a JPEG data URL without EXIF, GPS or text chunks, optionally mirrored left-right."""
    width, height = sent_size(image.width, image.height, max_side)
    rgb = image.convert("RGB")
    if (width, height) != rgb.size:
        rgb = rgb.resize((width, height), Image.Resampling.LANCZOS)
    if mirrored:
        rgb = ImageOps.mirror(rgb)
    clean = Image.frombytes("RGB", rgb.size, rgb.tobytes())
    output = BytesIO()
    clean.save(output, format="JPEG", quality=90)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return SentImage(
        data_url=f"data:image/jpeg;base64,{encoded}",
        width=width,
        height=height,
        source_width=image.width,
        source_height=image.height,
        mirrored=mirrored,
    )
