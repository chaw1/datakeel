# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Estimate the connected paper around OCR without counting a photograph's surroundings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageOps

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.transcription_auto import AutoRoutingConfig


_FILLED = 2


def _paper_mask(
    pixels: NDArray[np.uint8],
    box: NDArray[np.float64],
    config: AutoRoutingConfig,
    *,
    bridge: bool = False,
) -> NDArray[np.bool_]:
    source = Image.fromarray(pixels)
    scale = min(1.0, config.document_analysis_max_side / max(source.size))
    source.thumbnail((config.document_analysis_max_side, config.document_analysis_max_side))
    small = np.asarray(source)
    x1, y1, x2, y2 = box * scale
    height = y2 - y1
    left, top = max(0, int(x1 - height)), max(0, int(y1 - height))
    patch = small[top : int(np.ceil(y2 + height)), left : int(np.ceil(x2 + height))]
    background = float(np.percentile(patch, config.background_percentile))
    bright = small >= background - config.document_min_contrast
    if bridge:
        bright = np.maximum.accumulate(bright) & np.maximum.accumulate(bright[::-1])[::-1]
    component = Image.fromarray(bright.astype(np.uint8)).copy()
    valid = bright[top : top + patch.shape[0], left : left + patch.shape[1]]
    seed_y, seed_x = np.unravel_index(int(np.argmax(valid)), valid.shape)
    seed = (left + int(seed_x), top + int(seed_y))
    ImageDraw.floodfill(component, seed, _FILLED)
    connected = Image.fromarray((np.asarray(component) == _FILLED).astype(np.uint8))
    padded = ImageOps.expand(connected, border=1)
    ImageDraw.floodfill(padded, (0, 0), _FILLED)
    filled = Image.fromarray((np.asarray(padded)[1:-1, 1:-1] != _FILLED).astype(np.uint8))
    return (
        np.asarray(filled.resize((pixels.shape[1], pixels.shape[0]), Image.Resampling.NEAREST)) != 0
    )


def document_view(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> tuple[NDArray[np.uint8], int]:
    """Separate density area from conservative paper scope, retaining edge-touching figures."""
    mask = _paper_mask(pixels, boxes[0], config)
    padding = float(np.median(boxes[:, 3] - boxes[:, 1])) * config.document_padding_height_ratio
    # Only an edge-leaking component needs an OCR-envelope fallback.
    left = max(0, int(np.min(boxes[:, 0]) - padding))
    top = max(0, int(np.min(boxes[:, 1]) - padding))
    right = min(pixels.shape[1], int(np.ceil(np.max(boxes[:, 2]) + padding)))
    bottom = min(pixels.shape[0], int(np.ceil(np.max(boxes[:, 3]) + padding)))
    area = int(np.count_nonzero(mask))
    leaks = any(np.any(edge) for edge in (mask[0], mask[-1], mask[:, 0], mask[:, -1]))
    covered = all(
        np.any(mask[int(y1) : int(np.ceil(y2)), int(x1) : int(np.ceil(x2))])
        for x1, y1, x2, y2 in boxes
    )
    if not covered or (leaks and area / pixels.size < config.document_min_component_area_ratio):
        envelope = (bottom - top) * (right - left)
        area = min(area, envelope) if covered else envelope
    if covered and not leaks:
        pixels = np.where(_paper_mask(pixels, boxes[0], config, bridge=True), pixels, np.uint8(255))
    return pixels, area
