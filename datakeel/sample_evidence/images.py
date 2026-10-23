# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate distinct low-frequency textures and controlled image perturbations."""

import numpy as np
from PIL import Image

from datakeel.sample_evidence.models import Transformation

IMAGE_SIZE = (192, 128)
CHAIN_MINIMUM_SAMPLES = 100


def synthetic_image(index: int, *, dark: bool) -> Image.Image:
    """Create a reproducible smooth texture whose identity survives mild edits."""
    rng = np.random.default_rng(17 + index)
    pixels = rng.integers(45, 235, (10, 14, 3), dtype=np.uint8)
    image = Image.fromarray(pixels).resize(IMAGE_SIZE, Image.Resampling.BICUBIC)
    if dark:
        image = Image.fromarray((np.asarray(image).astype(np.float32) * 0.18).astype(np.uint8))
    return image


def perturb_image(image: Image.Image, transformation: Transformation, index: int) -> Image.Image:
    """Apply a deterministic, non-identical crop, resampling, or bounded noise edit."""
    if transformation == "crop":
        return image.crop((1, 1, image.width - 1, image.height - 1)).resize(
            IMAGE_SIZE, Image.Resampling.BICUBIC
        )
    if transformation == "resize":
        return image.resize((189, 125), Image.Resampling.BILINEAR).resize(
            IMAGE_SIZE, Image.Resampling.BILINEAR
        )
    rng = np.random.default_rng(100_017 + index)
    noise = rng.integers(-2, 3, (image.height, image.width, 3), dtype=np.int16)
    pixels = np.asarray(image).astype(np.int16) + noise
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def chain_indices(samples: int) -> tuple[int, ...]:
    """Reserve three distinct samples outside the ordinary duplicate sources."""
    if samples < CHAIN_MINIMUM_SAMPLES:
        return ()
    train_count = samples * 4 // 5
    return (train_count - 2, train_count - 1, train_count + samples // 20)


def chain_image(position: int) -> Image.Image:
    """Encode hashes at distances 6, 6, and 12 with identical four-bit prefixes.

    Each row integrates eight signed luminance steps. Nearest-neighbor expansion
    preserves those strict comparisons after 9x8 Lanczos dHash downsampling.
    Flipping two disjoint groups of six signs makes the chain non-transitive.
    """
    bits = np.random.default_rng(200_017).integers(0, 2, (8, 8)).reshape(-1)
    bits[4 : 4 + position * 6] = 1 - bits[4 : 4 + position * 6]
    steps = np.where(bits.reshape(8, 8), 18, -18)
    grid = np.concatenate([np.zeros((8, 1)), np.cumsum(steps, axis=1)], axis=1)
    grid = grid - grid.mean(axis=1, keepdims=True) + 128
    return (
        Image.fromarray(grid.astype(np.uint8))
        .resize(IMAGE_SIZE, Image.Resampling.NEAREST)
        .convert("RGB")
    )
