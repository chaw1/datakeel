# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Route OCR by deterministic pixel and geometry signals without invoking a backend."""

from __future__ import annotations

import re
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from datakeel.core.transcription_auto import AutoReason, AutoRouteDecision, AutoRoutingConfig

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.transcription_models import ImageInput, OCRLine, TranscriptionResult

_ARROW = re.compile(r"[←-⇿⟵-⟿]|-{1,3}>|<-{1,3}")


def _pixels(image: ImageInput, config: AutoRoutingConfig) -> tuple[NDArray[np.uint8], float]:
    with Image.open(BytesIO(image.png)) as source:
        grey = source.convert("L")
        scale = min(1.0, config.analysis_max_side / max(grey.size))
        if scale < 1:
            grey = grey.resize(
                (max(1, round(grey.width * scale)), max(1, round(grey.height * scale)))
            )
        return np.asarray(grey, dtype=np.uint8), scale


def _boxes(lines: tuple[OCRLine, ...], scale: float) -> NDArray[np.float64]:
    return np.asarray([tuple(value * scale for value in line.bbox) for line in lines])


def _masked_ink(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> NDArray[np.bool_]:
    ink = pixels < config.dark_pixel_threshold
    for x1, y1, x2, y2 in boxes:
        padding = (y2 - y1) * config.text_mask_padding_ratio
        left, top = max(0, int(x1 - padding)), max(0, int(y1 - padding))
        right, bottom = int(np.ceil(x2 + padding)), int(np.ceil(y2 + padding))
        ink[top:bottom, left:right] = False
    return ink


def _longest_run(values: NDArray[np.bool_]) -> int:
    padded = np.concatenate((np.array([False]), values, np.array([False])))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return int(np.max(changes[1::2] - changes[::2], initial=0))


def _axis_connector(
    ink: NDArray[np.bool_], pair: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    height = float(np.median(pair[:, 3] - pair[:, 1]))
    for axis in (0, 1):
        first, second = pair[np.argsort(pair[:, axis])]
        start, end = int(first[axis + 2]), int(second[axis])
        perpendicular = 1 - axis
        margin = height * config.connector_projection_margin_ratio
        left = max(0, int(max(first[perpendicular], second[perpendicular]) - margin))
        right = int(min(first[perpendicular + 2], second[perpendicular + 2]) + margin)
        if end - start < height * config.connector_min_height_ratio or right <= left:
            continue
        area = ink[start:end, left:right] if axis == 1 else ink[left:right, start:end].T
        if any(
            _longest_run(column) >= (end - start) * config.connector_min_coverage
            for column in area.T
        ):
            return True
    return False


def _connector(
    ink: NDArray[np.bool_], pair: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    if _axis_connector(ink, pair, config):
        return True
    centers: NDArray[np.float64] = (pair[:, :2] + pair[:, 2:]) / 2
    delta: NDArray[np.float64] = centers[1] - centers[0]
    distance = float(np.hypot(delta[0], delta[1]))
    height = float(np.median(pair[:, 3] - pair[:, 1]))
    if distance < height * config.connector_min_height_ratio:
        return False
    fractions = np.linspace(0, 1, max(2, int(np.ceil(distance))), dtype=np.float64)
    samples: NDArray[np.float64] = centers[0] + fractions[:, None] * delta
    outside = np.ones(len(samples), dtype=np.bool_)
    for x1, y1, x2, y2 in pair:
        outside &= ~(
            (samples[:, 0] >= x1)
            & (samples[:, 0] <= x2)
            & (samples[:, 1] >= y1)
            & (samples[:, 1] <= y2)
        )
    indices = samples[outside].astype(np.intp)
    if len(indices) < height * config.connector_min_height_ratio:
        return False
    tolerance = round(height * config.connector_tolerance_ratio)
    hits = np.zeros(len(indices), dtype=np.bool_)
    for offset in range(-tolerance, tolerance + 1):
        for axis in (0, 1):
            points = indices.copy()
            points[:, axis] += offset
            x = np.clip(points[:, 0], 0, ink.shape[1] - 1)
            y = np.clip(points[:, 1], 0, ink.shape[0] - 1)
            hits |= ink[y, x]
    return _longest_run(hits) >= len(hits) * config.connector_min_coverage


def _has_structure(
    ink: NDArray[np.bool_], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    # Compare nearby lines first; distant document lines cannot hide a local connector.
    centers: NDArray[np.float64] = (boxes[:, :2] + boxes[:, 2:]) / 2
    for index, center in enumerate(centers):
        distances: NDArray[np.float64] = np.sum((centers - center) ** 2, axis=1, dtype=np.float64)
        for other in np.argsort(distances)[1 : config.max_connector_neighbors + 1]:
            if other > index and _connector(ink, boxes[[index, other]], config):
                return True
    return False


def _has_strike(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    for x1, y1, x2, y2 in boxes:
        margin = (y2 - y1) * config.strike_vertical_margin
        area = pixels[int(y1 + margin) : int(y2 - margin) + 1, int(x1) : int(np.ceil(x2))]
        if any(
            _longest_run(row < config.dark_pixel_threshold)
            >= (x2 - x1) * config.strike_min_width_ratio
            for row in area
        ):
            return True
    return False


def _has_grey_row(
    pixels: NDArray[np.uint8], boxes: NDArray[np.float64], config: AutoRoutingConfig
) -> bool:
    background = float(np.percentile(pixels, config.background_percentile))
    text_brightness: list[float] = []
    for x1, y1, x2, y2 in boxes:
        context = (y2 - y1) * config.grey_context_height_ratio
        left, right = max(0, int(x1 - context)), min(pixels.shape[1], int(x2 + context))
        top, bottom = max(0, int(y1 - context)), min(pixels.shape[0], int(y2 + context) + 1)
        area = pixels[top:bottom, left:right]
        grey = (area >= config.grey_min_brightness) & (
            area <= min(config.grey_max_brightness, background - config.grey_min_contrast)
        )
        if grey.size and float(np.mean(grey)) >= config.grey_min_row_fraction:
            return True
        text = pixels[int(y1) : int(np.ceil(y2)), int(x1) : int(np.ceil(x2))]
        foreground = text[text < background - config.grey_min_contrast]
        if foreground.size:
            text_brightness.append(float(np.median(foreground)))
    return bool(text_brightness) and max(text_brightness) >= max(
        config.grey_min_text_brightness, min(text_brightness) + config.grey_min_contrast
    )


def _is_sparse(
    pixels: NDArray[np.uint8],
    ink: NDArray[np.bool_],
    boxes: NDArray[np.float64],
    characters: int,
    config: AutoRoutingConfig,
) -> bool:
    area = float(np.sum((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])))
    height = float(np.median(boxes[:, 3] - boxes[:, 1]))
    dark = int(np.count_nonzero(pixels < config.dark_pixel_threshold))
    unmatched = int(np.count_nonzero(ink)) / max(1, dark)
    return (
        (
            characters <= config.sparse_max_characters
            and area / pixels.size < config.min_text_area_ratio
        )
        or area / max(1, characters * height**2) > config.max_box_area_per_character
        or (dark > 0 and unmatched > config.max_unmatched_ink_fraction)
    )


def decide_auto_route(
    image: ImageInput,
    ocr: TranscriptionResult | None,
    config: AutoRoutingConfig | None = None,
) -> AutoRouteDecision:
    """Choose local OCR or vision from pixels and the completed local OCR attempt.

    ``None`` represents a caught OCR exception. Failure decisions never need to
    decode pixels; the caller remains responsible for authorization before vision.
    """
    config = config or AutoRoutingConfig()
    if (
        ocr is None
        or ocr.error
        or ocr.quality_issues
        or ocr.finish_reason == "length"
        or not ocr.text.strip()
        or not ocr.lines
    ):
        return AutoRouteDecision(route="vlm", reasons=("ocr_failed",))
    lines = tuple(line for line in ocr.lines if line.text.strip())
    if not lines:
        return AutoRouteDecision(route="vlm", reasons=("ocr_failed",))
    reasons: list[AutoReason] = []
    characters = sum(len(line.text.strip()) for line in lines)
    confidence = sum(line.confidence * len(line.text.strip()) for line in lines) / characters
    if confidence < config.min_mean_confidence:
        reasons.append("low_confidence")
    pixels, scale = _pixels(image, config)
    boxes = _boxes(lines, scale)
    ink = _masked_ink(pixels, boxes, config)
    if _ARROW.search(ocr.text) or _has_structure(ink, boxes, config):
        reasons.append("structure_diagram")
    if _has_strike(pixels, boxes, config) or _has_grey_row(pixels, boxes, config):
        reasons.append("struck_or_greyed_rows")
    if _is_sparse(pixels, ink, boxes, characters, config):
        reasons.append("sparse_text")
    return AutoRouteDecision(
        route="vlm" if reasons else "ocr", reasons=tuple(reasons) or ("clean_text",)
    )
