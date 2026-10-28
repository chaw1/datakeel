# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep local cancellation evidence distinct from paper and photograph appearance."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from datakeel.core.transcription_auto import AutoRoutingConfig
from datakeel.transcription.auto_rows import has_grey_row, has_strike

if TYPE_CHECKING:
    from numpy.typing import NDArray

FONT = ImageFont.load_default(size=22)
CONFIG = AutoRoutingConfig()


def _row(canvas: Image.Image, y: int, *, x: int = 35, ink: int = 0) -> tuple[int, int, int, int]:
    draw = ImageDraw.Draw(canvas)
    text = "The current register belongs to Maple Laboratory"
    draw.text((x, y), text, font=FONT, fill=ink)
    return draw.textbbox((x, y), text, font=FONT)


def _pixels(canvas: Image.Image) -> NDArray[np.uint8]:
    return np.asarray(canvas, dtype=np.uint8)


@pytest.mark.parametrize("brightness", [120, 170, 230])
def test_aligned_adjacent_grey_background_is_row_state(brightness: int) -> None:
    """A locally shaded row next to a normal aligned row carries cancellation state."""
    canvas = Image.new("L", (700, 300), 255)
    ImageDraw.Draw(canvas).rectangle((20, 130, 680, 190), fill=brightness)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150)], dtype=np.float64)
    assert has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("brightness", [120, 170, 215, 245])
@pytest.mark.parametrize("noise", [0, 12, 28])
def test_uniform_grey_noisy_paper_is_not_row_state(brightness: int, noise: int) -> None:
    """Whole-page paper colour and grain remain independent of local row semantics."""
    rng = np.random.default_rng(7821)
    pixels = np.clip(rng.normal(brightness, noise, size=(300, 700)), 0, 255).astype(np.uint8)
    canvas = Image.fromarray(pixels)
    ImageDraw.Draw(canvas).rectangle((0, 0, 699, 299), outline=70, width=18)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("brightness", [120, 150, 190])
def test_faded_foreground_compares_aligned_neighbour_contrast(brightness: int) -> None:
    """Different foreground ink on the same paper is a state signal within the group."""
    canvas = Image.new("L", (700, 300), 255)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150, ink=brightness)], dtype=np.float64)
    assert has_grey_row(_pixels(canvas), boxes, CONFIG)


def test_uniform_low_contrast_text_is_not_row_state() -> None:
    """A consistently faint paragraph supplies no contrasting normal row."""
    canvas = Image.new("L", (700, 300), 205)
    boxes = np.asarray([_row(canvas, y, ink=135) for y in (40, 150)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


def test_isolated_grey_row_cannot_infer_state_without_neighbour() -> None:
    """A single local grey area may be ordinary paper, not a disabled list entry."""
    canvas = Image.new("L", (700, 300), 255)
    ImageDraw.Draw(canvas).rectangle((20, 30, 680, 90), fill=180)
    boxes = np.asarray([_row(canvas, 40)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


def test_different_columns_do_not_compare_foreground_state() -> None:
    """Text from an unrelated column cannot supply a normal row for faded print."""
    canvas = Image.new("L", (1100, 300), 255)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150, x=550, ink=150)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


def test_large_faded_heading_is_not_a_disabled_body_row() -> None:
    """A different typographic group cannot be the normal reference for a grey heading."""
    canvas = Image.new("L", (1000, 300), 255)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=42)
    text = "The current register"
    draw.text((35, 40), text, font=font, fill=150)
    heading = draw.textbbox((35, 40), text, font=font)
    boxes = np.asarray([heading, _row(canvas, 150)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("amplitude", [40, 90, 140])
def test_smooth_shadow_between_aligned_rows_is_not_state(amplitude: int) -> None:
    """Neighbour rows under a gradual photographic shadow lack a local shading boundary."""
    gradient = np.linspace(255, 255 - amplitude, 300, dtype=np.uint8)
    canvas = Image.fromarray(np.repeat(gradient[:, None], 700, axis=1))
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150)], dtype=np.float64)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("width", [6, 10, 15])
@pytest.mark.parametrize("scale", [0.5, 1, 2, 4])
def test_steep_continuous_shadow_is_not_a_shaded_row(width: int, scale: float) -> None:
    """A smooth but steep photographic shadow lacks a concentrated row-state boundary."""
    y = np.arange(300, dtype=np.float64)[:, None]
    pixels = np.broadcast_to(205 - 50 * np.tanh((y - 110) / width), (300, 700)).astype(np.uint8)
    canvas = Image.fromarray(pixels.copy())
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150)], dtype=np.float64) * scale
    canvas = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)))
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("brightness", [130, 180, 230])
@pytest.mark.parametrize("scale", [0.5, 1, 2, 4])
def test_shaded_row_boundary_survives_rendering_scale(brightness: int, scale: float) -> None:
    """Blurred resampling of a true row boundary retains its local contrast signal."""
    canvas = Image.new("L", (700, 300), 255)
    ImageDraw.Draw(canvas).rectangle((20, 130, 680, 190), fill=brightness)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 150)], dtype=np.float64) * scale
    canvas = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)))
    assert has_grey_row(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("fraction", [0.76, 0.9, 1.0])
@pytest.mark.parametrize("paper", [120, 150, 235])
def test_thin_central_cancellation_stroke_is_row_state(fraction: float, paper: int) -> None:
    """A thin stroke over most of the text remains a positive cancellation signal."""
    canvas = Image.new("L", (700, 300), paper)
    box = _row(canvas, 70)
    x1, y1, x2, y2 = box
    ImageDraw.Draw(canvas).line(
        (x1, (y1 + y2) / 2, x1 + (x2 - x1) * fraction, (y1 + y2) / 2), fill=0, width=2
    )
    assert has_strike(_pixels(canvas), np.asarray([box], dtype=np.float64), CONFIG)


@pytest.mark.parametrize("overrun", [2, 4, 6, 10])
@pytest.mark.parametrize("scale", [0.5, 1, 2])
def test_true_cancellation_can_extend_slightly_beyond_text_box(overrun: int, scale: float) -> None:
    """A real strike can overrun the glyph rectangle without becoming an exterior texture."""
    canvas = Image.new("L", (700, 300), 255)
    box = _row(canvas, 70)
    x1, y1, x2, y2 = box
    ImageDraw.Draw(canvas).line(
        (x1 - overrun, (y1 + y2) / 2, x2 + overrun, (y1 + y2) / 2), fill=0, width=2
    )
    canvas = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)))
    boxes = np.asarray([box], dtype=np.float64) * scale
    assert has_strike(_pixels(canvas), boxes, CONFIG)


@pytest.mark.parametrize("kind", ["underline", "above", "short", "thick", "texture"])
def test_decorations_and_background_stripes_are_not_cancellation(kind: str) -> None:
    """Cancellation must be thin, central, long, and confined to the text extent."""
    canvas = Image.new("L", (700, 300), 235)
    box = _row(canvas, 70)
    x1, y1, x2, y2 = box
    y, left, right, width = (y1 + y2) / 2, x1, x2, 2
    if kind == "underline":
        y = y2 + 5
    elif kind == "above":
        y = y1 - 5
    elif kind == "short":
        right = x1 + (x2 - x1) / 3
    elif kind == "thick":
        width = y2 - y1
    else:
        left, right = 0, 699
    ImageDraw.Draw(canvas).line((left, y, right, y), fill=0, width=width)
    assert not has_strike(_pixels(canvas), np.asarray([box], dtype=np.float64), CONFIG)


def test_texture_outside_text_does_not_supply_row_evidence() -> None:
    """Dark table-like stripes beyond OCR text are not local row state."""
    canvas = Image.new("L", (700, 300), 235)
    draw = ImageDraw.Draw(canvas)
    for y in range(195, 300, 8):
        draw.line((0, y, 699, y), fill=30, width=2)
    boxes = np.asarray([_row(canvas, 40), _row(canvas, 120)], dtype=np.float64)
    assert not has_strike(_pixels(canvas), boxes, CONFIG)
    assert not has_grey_row(_pixels(canvas), boxes, CONFIG)


def test_empty_or_outside_geometry_has_no_row_evidence() -> None:
    """A malformed region must not acquire cancellation evidence from empty arrays."""
    pixels = np.full((100, 100), 255, dtype=np.uint8)
    boxes = np.asarray([[200, 20, 230, 40], [200, 50, 230, 70]], dtype=np.float64)
    assert not has_strike(pixels, boxes, CONFIG)
    assert not has_grey_row(pixels, boxes, CONFIG)
