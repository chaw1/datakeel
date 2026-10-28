# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded, scale-normalized image signals without learned image classifiers."""

from math import ceil, sqrt

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from datakeel.core.models import Record

_LUMINANCE = np.array([0.299, 0.587, 0.114], dtype=np.float32)
_NOISE_SAMPLE_SIDE = 1024
_NOISE_PATCH_SIDE = 2
_RGBA_CHANNELS = 4
_NORMAL_MAD_SCALE = 1.3489795003921634
_DARK_LEVEL = 5
_BRIGHT_LEVEL = 250
_HIGHLIGHT_QUANTILE = 0.999
_ROUNDING_VARIANCE = 1 / 12
_IMPULSE_TILE = 256
_IMPULSE_TILES_PER_SIDE = 4
_NEIGHBOR_OFFSETS = tuple(
    (row, column) for row in range(3) for column in range(3) if (row, column) != (1, 1)
)


class ImageSignals(Record):
    """Carry current oriented-pixel measurements across the scoring boundary."""

    width: int
    height: int
    blur_variance: float
    normalized_blur_variance: float
    sharpness: float | None = None
    brightness: float
    highlight: float = 255.0
    dark_fraction: float
    bright_fraction: float
    noise_sigma: float
    impulse_fraction: float = 0.0
    color_stddev: float
    bit_depth: int = 8
    analysis_width: int
    analysis_height: int


def _laplacian(gray: NDArray[np.float32]) -> NDArray[np.float32]:
    padded = np.pad(gray, 1, mode="edge")
    return padded[1:-1, :-2] + padded[1:-1, 2:] + padded[:-2, 1:-1] + padded[2:, 1:-1] - 4 * gray


def _laplacian_variance(gray: NDArray[np.float32]) -> float:
    return float(_laplacian(gray).var())


def _sharpness(gray: NDArray[np.float32], scale: float) -> float | None:
    """Return the root ratio of Laplacian energy to gradient energy above the rounding floor.

    Scaling every intensity, as low contrast, haze or underexposure do,
    scales both energies alike, so the ratio depends only on how wide edges
    are. A crisp step scores about 1.4 and wider blur scores lower. Rounding
    to 8-bit levels adds white error of variance 1/12, reduced by averaging
    when the image is shrunk; its expected energy is removed first so that
    faint, blurred content cannot look sharp through its stair steps. An
    image without gradient energy above that floor returns None.
    """
    variance = _ROUNDING_VARIANCE * scale * scale
    across, down = np.diff(gray, axis=1), np.diff(gray, axis=0)
    gradient = float(np.square(across, dtype=np.float64).sum())
    gradient += float(np.square(down, dtype=np.float64).sum())
    gradient -= 2 * variance * (across.size + down.size)
    laplacian = float(np.square(_laplacian(gray), dtype=np.float64).sum())
    laplacian -= 20 * variance * gray.size
    if gradient <= 0:
        return None
    return sqrt(max(0.0, laplacian) / gradient)


def _noise_sigma(pixels: NDArray[np.uint8]) -> float:
    height, width = pixels.shape[:2]
    if min(height, width) < _NOISE_PATCH_SIDE:
        return 0.0
    step = max(1, ceil(max(height, width) / _NOISE_SAMPLE_SIDE))
    # Adjacent 2x2 diagonal differences cancel smooth gradients. Their median
    # rejects sparse edges; Gaussian pixel noise has median absolute value 1.349 sigma.
    diagonal = (
        pixels[:-1:step, :-1:step, :3].astype(np.float32)
        - pixels[1::step, :-1:step, :3]
        - pixels[:-1:step, 1::step, :3]
        + pixels[1::step, 1::step, :3]
    )
    return float(np.median(np.abs(diagonal))) / _NORMAL_MAD_SCALE


def _tile_starts(length: int) -> NDArray[np.intp]:
    count = ceil(max(0, length - 2) / _IMPULSE_TILE)
    if count <= _IMPULSE_TILES_PER_SIDE:
        return np.arange(count, dtype=np.intp) * _IMPULSE_TILE
    last = length - _IMPULSE_TILE - 2
    return np.linspace(0, last, _IMPULSE_TILES_PER_SIDE).round().astype(np.intp)


def _impulses(region: NDArray[np.uint8], level: float) -> tuple[int, int]:
    """Count interior pixels unlike their 3x3 median and unlike every neighbor."""
    values = region[..., :3].astype(np.float32)
    height, width = values.shape[0] - 2, values.shape[1] - 2
    center = values[1:-1, 1:-1]
    neighbors = np.stack(
        [values[row : row + height, column : column + width] for row, column in _NEIGHBOR_OFFSETS]
    )
    window = np.concatenate([neighbors, center[None]])
    median = np.partition(window, 4, axis=0)[4]
    closest = np.abs(neighbors - center[None]).min(axis=0)
    hits = (np.abs(center - median) > level) & (closest > level / 2)
    return int(hits.any(axis=2).sum()), height * width


def _impulse_fraction(pixels: NDArray[np.uint8], level: float) -> float:
    """Measure salt-and-pepper pixels on native tiles, sampling at most 16 large tiles.

    Requiring a difference from every neighbor, not only from the median,
    keeps one-pixel lines and text strokes from counting as impulses.
    """
    height, width = pixels.shape[:2]
    hits = total = 0
    for top in _tile_starts(height):
        for left in _tile_starts(width):
            region = pixels[top : top + _IMPULSE_TILE + 2, left : left + _IMPULSE_TILE + 2]
            found, counted = _impulses(region, level)
            hits, total = hits + found, total + counted
    return hits / total if total else 0.0


def measure(
    pixels: NDArray[np.uint8], analysis_size: int, impulse_level: float = 48.0, bit_depth: int = 8
) -> ImageSignals:
    """Measure native noise and exposure, with sharpness at a common spatial scale.

    Larger images are reduced so the longest side equals ``analysis_size``.
    Smaller images are measured natively: interpolating them upward would
    fabricate blur and confuse low resolution with an unsharp capture.
    Pixels arrive as 8-bit levels whatever the source bit depth.
    """
    if pixels.shape[2] == _RGBA_CHANNELS:
        rgba = Image.fromarray(pixels)
        pixels = np.array(Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba))
    height, width = pixels.shape[:2]
    gray: NDArray[np.float32] = np.dot(pixels[..., :3], _LUMINANCE)
    scale = min(1.0, analysis_size / max(width, height))
    dimensions = (max(1, round(width * scale)), max(1, round(height * scale)))
    raster = Image.fromarray(pixels[..., :3]).resize(dimensions, Image.Resampling.LANCZOS)
    normalized = np.asarray(raster).astype(np.float32)
    # Resample luminance in floating point: rounding the reduced image back to
    # 8-bit levels would add stair steps that look like edges in faint scenes.
    analysis_gray: NDArray[np.float32] = np.asarray(
        Image.fromarray(gray, "F").resize(dimensions, Image.Resampling.LANCZOS)
    )
    return ImageSignals(
        width=width,
        height=height,
        blur_variance=round(_laplacian_variance(gray), 3),
        normalized_blur_variance=_laplacian_variance(analysis_gray),
        sharpness=_sharpness(analysis_gray, scale),
        brightness=round(float(gray.mean()), 3),
        highlight=float(np.quantile(gray, _HIGHLIGHT_QUANTILE)),
        dark_fraction=float(np.count_nonzero(gray <= _DARK_LEVEL) / gray.size),
        bright_fraction=float(np.count_nonzero(gray >= _BRIGHT_LEVEL) / gray.size),
        noise_sigma=_noise_sigma(pixels),
        impulse_fraction=_impulse_fraction(pixels, impulse_level),
        color_stddev=float(np.max(np.std(normalized, axis=(0, 1)))),
        bit_depth=bit_depth,
        analysis_width=dimensions[0],
        analysis_height=dimensions[1],
    )
