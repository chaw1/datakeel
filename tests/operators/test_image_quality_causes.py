# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated photographs check that each image defect is reported with its own cause."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from datakeel.operators import REGISTRY
from datakeel.operators.base import ImageQualityParams
from datakeel.operators.image.quality import ImageQualityMeasurement

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from tests.operators.factories import FileFactory

DEFAULTS = ImageQualityParams()
SEEDS = (0, 1, 2)


def _pink(rng: np.random.Generator, height: int, width: int) -> NDArray[np.float64]:
    """Return 1/f texture, the spectrum of natural scenes, scaled to [0, 1]."""
    frequency = np.hypot(np.fft.rfftfreq(width)[None, :], np.fft.fftfreq(height)[:, None])
    frequency[0, 0] = 1
    spectrum = (
        rng.normal(size=frequency.shape) + 1j * rng.normal(size=frequency.shape)
    ) / frequency
    texture = np.fft.irfft2(spectrum, s=(height, width))
    texture -= texture.min()
    return texture / texture.max()


def _photo(seed: int, size: tuple[int, int] = (512, 384)) -> NDArray[np.float64]:
    """Render textured ground with solid objects at twice the size, then reduce it."""
    rng = np.random.default_rng(seed)
    width, height = size
    texture = np.stack([_pink(rng, height * 2, width * 2) for _ in range(3)], axis=-1)
    canvas = Image.fromarray((texture * rng.uniform(0.3, 1, 3) * 200 + 25).astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    for _ in range(14):
        left, top = rng.uniform(0, width * 2, 2)
        across, down = rng.uniform(40, 500, 2)
        color = tuple(int(value) for value in rng.integers(0, 256, 3))
        shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
        shape([left, top, left + across, top + down], fill=color)
    reduced = canvas.resize(size, Image.Resampling.LANCZOS)
    return np.asarray(reduced).astype(np.float64)


def _image(levels: NDArray[np.float64]) -> Image.Image:
    return Image.fromarray(np.clip(np.round(levels), 0, 255).astype(np.uint8))


def _quality(
    image: Image.Image, make_file: FileFactory, output_dir: Path
) -> ImageQualityMeasurement:
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    file = make_file(encoded.getvalue(), "generated.png", "image")
    result = REGISTRY["image.quality"].run([file], output_dir)
    return ImageQualityMeasurement.model_validate(result.files[0].metadata["image_quality"])


@pytest.mark.parametrize("seed", SEEDS)
def test_salt_and_pepper_is_found_by_impulse_fraction(
    make_file: FileFactory, output_dir: Path, seed: int
) -> None:
    """Five percent saturated pixels fail noise although their robust sigma stays low."""
    photo = _photo(seed)
    clean = _quality(_image(photo), make_file, output_dir)
    assert clean.impulse_fraction < DEFAULTS.max_impulse_fraction / 10
    assert clean.checks.noise.failed is False
    rng = np.random.default_rng(9)
    hit = rng.random(photo.shape[:2]) < 0.05
    noisy = photo.copy()
    noisy[hit] = (rng.random((int(hit.sum()), 1)) < 0.5) * 255.0
    measured = _quality(_image(noisy), make_file, output_dir)
    assert measured.impulse_fraction > 0.03
    assert measured.noise_sigma < DEFAULTS.max_noise_sigma
    assert measured.checks.noise.failed is True
    assert "impulse pixel fraction" in measured.checks.noise.reason
    assert measured.checks.noise.reason in measured.reasons


def test_thin_lines_and_text_strokes_are_not_impulses(
    make_file: FileFactory, output_dir: Path
) -> None:
    """One-pixel strokes differ from their median but match a neighbor along the stroke."""
    canvas = _image(_photo(3))
    draw = ImageDraw.Draw(canvas)
    for row in range(20, 380, 9):
        draw.line([(10, row), (500, row + 3)], fill=(250, 250, 250), width=1)
    draw.text((30, 30), "Datakeel 0123456789 quality", fill=(0, 0, 0))
    measured = _quality(canvas, make_file, output_dir)
    assert measured.impulse_fraction < DEFAULTS.max_impulse_fraction / 3
    assert measured.checks.noise.failed is False


@pytest.mark.parametrize("seed", SEEDS)
def test_low_contrast_photo_is_sharp_and_its_blurred_copy_is_not(
    make_file: FileFactory, output_dir: Path, seed: int
) -> None:
    """Edge width, not edge strength, decides blur, so haze alone is not blur."""
    photo = _photo(seed)
    faint = 128 + (photo - photo.mean()) * 0.25
    sharp = _quality(_image(faint), make_file, output_dir)
    assert sharp.checks.blur.failed is False
    assert sharp.sharpness is not None
    assert sharp.sharpness > DEFAULTS.min_sharpness * 1.2
    blurred = _quality(_image(faint).filter(ImageFilter.GaussianBlur(2)), make_file, output_dir)
    assert blurred.checks.blur.failed is True
    assert blurred.issues == ["blurry"]
    normal = _quality(_image(photo), make_file, output_dir)
    assert normal.sharpness == pytest.approx(sharp.sharpness, rel=0.1)


@pytest.mark.parametrize(("factor", "by_mean"), [(0.1, True), (0.45, False)])
def test_underexposure_is_reported_as_exposure_and_not_as_blur(
    make_file: FileFactory, output_dir: Path, factor: float, *, by_mean: bool
) -> None:
    """A dark frame fails exposure, by its mean or its dim highlights, and blur is not judged."""
    photo = _photo(1)
    assert _quality(_image(photo), make_file, output_dir).checks.exposure.failed is False
    dark = _quality(_image(photo * factor), make_file, output_dir)
    assert dark.checks.exposure.failed is True
    assert (dark.brightness < DEFAULTS.min_brightness) is by_mean
    assert dark.highlight < DEFAULTS.min_highlight
    assert "(underexposed)" in dark.checks.exposure.reason
    assert dark.checks.blur.failed is False
    assert "exposure failed" in dark.checks.blur.reason
    assert dark.issues == ["brightness"]


def _sixteen_bit(levels: NDArray[np.float64]) -> Image.Image:
    return Image.fromarray(np.clip(np.round(levels), 0, 65535).astype(np.uint16))


def test_sixteen_bit_gray_is_scaled_by_bit_depth(make_file: FileFactory, output_dir: Path) -> None:
    """A normal 16-bit frame is not white; a saturated one still fails exposure."""
    gray = _photo(2).mean(axis=2)
    normal = _quality(_sixteen_bit(gray * 257), make_file, output_dir)
    eight = _quality(_image(np.repeat(gray[..., None], 3, axis=2)), make_file, output_dir)
    assert normal.bit_depth == 16
    assert normal.brightness == pytest.approx(eight.brightness, abs=0.5)
    assert normal.checks.exposure.failed is False
    assert normal.bright_fraction < 0.01
    saturated = _quality(_sixteen_bit(gray * 257 * 2.5), make_file, output_dir)
    assert saturated.checks.exposure.failed is True
    assert saturated.bright_fraction > DEFAULTS.max_clipped_fraction
