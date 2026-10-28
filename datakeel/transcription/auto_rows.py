# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare row state only within local OCR text and aligned neighbouring rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.transcription_auto import AutoRoutingConfig


def _runs(values: NDArray[np.bool_]) -> NDArray[np.intp]:
    padded = np.concatenate(([False], values, [False]))
    return np.flatnonzero(padded[1:] != padded[:-1]).reshape(-1, 2)


def longest_run(values: NDArray[np.bool_]) -> int:
    """Measure contiguous ink identically for connectors and cancellation strokes."""
    return int(np.max(np.diff(_runs(values), axis=1), initial=0))


def has_strike(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    """Find thin central cancellation strokes, excluding continuous background stripes."""
    for x1, y1, x2, y2 in boxes:
        left, right = max(0, int(x1)), min(pixels.shape[1], int(np.ceil(x2)))
        top, bottom = max(0, int(y1)), min(pixels.shape[0], int(np.ceil(y2)))
        area = pixels[top:bottom, left:right]
        if not area.size:
            continue
        threshold = min(
            config.dark_pixel_threshold,
            float(np.percentile(area, config.background_percentile)) - config.grey_min_contrast,
        )
        width = (x2 - x1) * config.strike_min_width_ratio
        horizontal = np.fromiter((longest_run(row < threshold) >= width for row in area), np.bool_)
        margin = (y2 - y1) * config.strike_vertical_margin
        extension = max(1, round((y2 - y1) * config.strike_max_extension_ratio))
        for start, end in _runs(horizontal):
            if not margin <= (start + end) / 2 <= bottom - top - margin:
                continue
            if end - start > (y2 - y1) * config.strike_max_thickness_ratio:
                continue
            strip = pixels[top + start : top + end]
            outside = strip[:, max(0, left - extension) : right + extension]
            edges = outside[:, :extension], outside[:, -extension:]
            if any(np.all(edge < threshold) for edge in edges):
                continue
            return True
    return False


def _row_pair(
    pair: NDArray[np.float64], pixels: NDArray[np.uint8], config: AutoRoutingConfig
) -> bool:
    backgrounds: list[float] = []
    foregrounds: list[float] = []
    percentile = config.background_percentile
    for x1, y1, x2, y2 in pair:
        area = pixels[max(0, int(y1)) : int(np.ceil(y2)), max(0, int(x1)) : int(np.ceil(x2))]
        if not area.size:
            return False
        background = float(np.percentile(area, percentile))
        text = area[area < background - config.grey_min_contrast]
        backgrounds.append(background)
        text_level = float(np.percentile(text, 100 - percentile)) if text.size else background
        foregrounds.append(text_level)
    faded = int(np.argmax(foregrounds))
    normal = 1 - faded
    if (
        foregrounds[faded]
        >= max(config.grey_min_text_brightness, foregrounds[normal] + config.grey_min_contrast)
        and backgrounds[faded] - foregrounds[faded]
        <= backgrounds[normal] - foregrounds[normal] - config.grey_min_contrast
    ):
        return True
    upper = min(config.grey_max_brightness, max(backgrounds) - config.grey_min_contrast)
    if not config.grey_min_brightness <= min(backgrounds) <= upper:
        return False
    left, right = int(max(pair[:, 0])), int(min(pair[:, 2]))
    top, bottom = max(0, int(min(pair[:, 1]))), int(np.ceil(max(pair[:, 3])))
    area = pixels[top:bottom, max(0, left) : right]
    if not area.size:
        return False
    profile = np.percentile(area, percentile, axis=1)
    height = float(np.min(pair[:, 3] - pair[:, 1]))
    step = max(1, round(height * config.grey_background_step_height_ratio))
    probe = min(step, max(1, round(height * config.grey_edge_probe_height_ratio)))
    changes = np.abs(profile[step:] - profile[:-step])
    jumps = np.abs(profile[probe:] - profile[:-probe])
    peaks = np.lib.stride_tricks.sliding_window_view(jumps, step - probe + 1).max(axis=1)
    concentrated = changes[peaks >= changes * config.grey_min_edge_concentration]
    return bool(np.any(concentrated >= config.grey_min_contrast))


def has_grey_row(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    """Require a local state contrast between adjacent, consistently aligned text rows."""
    rows = boxes[np.argsort(boxes[:, 1])]
    for index, first in enumerate(rows):
        height = first[3] - first[1]
        for second in rows[index + 1 :]:
            distance = second[1] - first[3]
            if distance > height * config.grey_max_neighbor_height_ratio:
                break
            aligned = abs(first[0] - second[0]) <= height * config.grey_alignment_height_ratio
            overlap = min(first[2], second[2]) - max(first[0], second[0])
            heights = height, second[3] - second[1]
            same_size = max(heights) <= min(heights) * config.grey_max_line_height_ratio
            if distance < 0 or not aligned or overlap <= 0 or not same_size:
                continue
            if _row_pair(np.asarray([first, second]), pixels, config):
                return True
            break
    return False
