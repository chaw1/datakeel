# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded, scale-normalized image signals without learned image classifiers."""

from math import ceil

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


class ImageSignals(Record):
    """Carry current oriented-pixel measurements across the scoring boundary."""

    width: int
    height: int
    blur_variance: float
    normalized_blur_variance: float
    brightness: float
    dark_fraction: float
    bright_fraction: float
    noise_sigma: float
    color_stddev: float
    analysis_width: int
    analysis_height: int


def _laplacian_variance(gray: NDArray[np.float32]) -> float:
    padded = np.pad(gray, 1, mode="edge")
    laplacian = (
        padded[1:-1, :-2] + padded[1:-1, 2:] + padded[:-2, 1:-1] + padded[2:, 1:-1] - 4 * gray
    )
    return float(laplacian.var())


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


def measure(pixels: NDArray[np.uint8], analysis_size: int) -> ImageSignals:
    """Measure native noise and exposure, with sharpness at a common spatial scale.

    Larger images are reduced so the longest side equals ``analysis_size``.
    Smaller images are measured natively: interpolating them upward would
    fabricate blur and confuse low resolution with an unsharp capture.
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
    return ImageSignals(
        width=width,
        height=height,
        blur_variance=round(_laplacian_variance(gray), 3),
        normalized_blur_variance=_laplacian_variance(np.dot(normalized, _LUMINANCE)),
        brightness=round(float(gray.mean()), 3),
        dark_fraction=float(np.count_nonzero(gray <= _DARK_LEVEL) / gray.size),
        bright_fraction=float(np.count_nonzero(gray >= _BRIGHT_LEVEL) / gray.size),
        noise_sigma=_noise_sigma(pixels),
        color_stddev=float(np.max(np.std(normalized, axis=(0, 1)))),
        analysis_width=dimensions[0],
        analysis_height=dimensions[1],
    )
