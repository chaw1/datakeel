# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Draw independent scanned paragraphs and projectively transformed card photographs."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from datakeel.core.transcription_models import OCRLine, TranscriptionResult
from datakeel.transcription.images import normalize_image

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.transcription_models import ImageInput

_FONT = ImageFont.load_default(size=22)
_PARAGRAPH = (
    "The visitor register records the current room owners.",
    "Every printed entry was checked against the local list.",
    "Morning reviews keep the ordinary records up to date.",
    "The next review takes place after the weekly meeting.",
    "All details in this paragraph remain active and valid.",
    "Please retain this paper copy for the next inspection.",
)


def image_and_ocr(
    canvas: Image.Image, lines: tuple[OCRLine, ...]
) -> tuple[ImageInput, TranscriptionResult]:
    """Encode pixels and their independently known glyph rectangles without an OCR engine."""
    output = BytesIO()
    canvas.save(output, format="PNG")
    return normalize_image(output.getvalue()), TranscriptionResult(
        text="\n".join(line.text for line in lines),
        lines=lines,
        width=canvas.width,
        height=canvas.height,
        backend="ocr",
    )


def _paragraph(
    canvas: Image.Image, position: tuple[int, int], ink: int, *, short: bool = False
) -> tuple[OCRLine, ...]:
    draw = ImageDraw.Draw(canvas)
    texts = ("Room 312",) if short else _PARAGRAPH
    lines: list[OCRLine] = []
    for index, text in enumerate(texts):
        origin = position[0], position[1] + index * 48
        draw.text(origin, text, font=_FONT, fill=(ink,) * 3)
        lines.append(
            OCRLine(text=text, bbox=draw.textbbox(origin, text, font=_FONT), confidence=0.99)
        )
    return tuple(lines)


def scanned_paragraph(
    paper: int, noise: float, seed: int
) -> tuple[ImageInput, TranscriptionResult]:
    """Make grey paper, Gaussian noise, isolated grain and a darker scanner surround."""
    random = np.random.default_rng(seed)
    pixels = random.normal(paper, noise, (700, 900))
    grain = random.random(pixels.shape) < 0.015
    pixels[grain] -= noise * 2
    canvas = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 899, 699), outline=(max(20, paper - 70),) * 3, width=45)
    lines = _paragraph(canvas, (95, 125), 35)
    return image_and_ocr(canvas, lines)


def low_contrast_paragraph(
    paper: int, contrast: int, seed: int
) -> tuple[ImageInput, TranscriptionResult]:
    """Keep all ink uniformly faint but clear on lightly noisy unstructured paper."""
    random = np.random.default_rng(seed)
    pixels = random.normal(paper, 1.5, (460, 820))
    canvas = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).convert("RGB")
    return image_and_ocr(canvas, _paragraph(canvas, (45, 65), paper - contrast))


def incomplete_scanned_page(
    kind: Literal["figure", "label"],
) -> tuple[ImageInput, TranscriptionResult]:
    """Retain incomplete OCR evidence on a page with two partially visible scanner borders."""
    canvas = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 30, 999), fill=(95,) * 3)
    draw.rectangle((0, 970, 999, 999), fill=(110,) * 3)
    text = "One recognized label on an unrecognized figure" if kind == "figure" else "Label"
    draw.text((80, 60), text, font=_FONT, fill="black")
    line = OCRLine(text=text, bbox=draw.textbbox((80, 60), text, font=_FONT), confidence=0.99)
    if kind == "figure":
        draw.ellipse((150, 300, 900, 900), fill="black")
    return image_and_ocr(canvas, (line,))


def edge_touching_unrecognized_figure() -> tuple[ImageInput, TranscriptionResult]:
    """Draw unknown ink touching paper edges below an otherwise recognized paragraph."""
    canvas = Image.new("RGB", (900, 700), (70,) * 3)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((40, 40, 860, 660), fill=(230,) * 3)
    text = "One recognized paragraph above a large edge touching diagram."
    draw.text((80, 90), text, font=_FONT, fill="black")
    line = OCRLine(text=text, bbox=draw.textbbox((80, 90), text, font=_FONT), confidence=0.99)
    draw.rectangle((40, 240, 860, 600), fill="black")
    return image_and_ocr(canvas, (line,))


def dark_tabletop_card(surface: int) -> tuple[ImageInput, TranscriptionResult]:
    """Put a fully recognized card on a dark surface that can be darker than its ink."""
    canvas = Image.new("RGB", (1000, 800), (surface,) * 3)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((220, 180, 800, 600), fill="white")
    texts = (
        "Current visitor register",
        "All printed entries remain active",
        "Review the paper at the next meeting",
    )
    lines: list[OCRLine] = []
    for index, text in enumerate(texts):
        origin = 255, 235 + index * 80
        draw.text(origin, text, font=_FONT, fill=(30,) * 3)
        lines.append(
            OCRLine(text=text, bbox=draw.textbbox(origin, text, font=_FONT), confidence=0.99)
        )
    return image_and_ocr(canvas, tuple(lines))


def _tabletop(kind: Literal["stripes", "wood"], variant: int) -> Image.Image:
    y, x = np.indices((1100, 1400), dtype=np.float64)
    pixels = 220 + 19 * np.sin(y / (9 + variant))
    if kind == "wood":
        pixels += 8 * np.sin(y / 3 + np.sin(x / 90)) + 4 * np.sin(x / 130)
    pixels[(y.astype(np.intp) + variant * 3) % 63 < 3] = 112
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).convert("RGB")


def _project_boxes(
    lines: tuple[OCRLine, ...], transform: NDArray[np.float64]
) -> tuple[OCRLine, ...]:
    projected: list[OCRLine] = []
    for line in lines:
        x1, y1, x2, y2 = line.bbox
        corners = np.array(((x1, y1, 1), (x2, y1, 1), (x2, y2, 1), (x1, y2, 1)))
        mapped = corners @ transform.T
        mapped = mapped[:, :2] / mapped[:, 2:]
        bbox = (
            float(np.min(mapped[:, 0])),
            float(np.min(mapped[:, 1])),
            float(np.max(mapped[:, 0])),
            float(np.max(mapped[:, 1])),
        )
        projected.append(line.model_copy(update={"bbox": bbox}))
    return tuple(projected)


def card_photograph(
    kind: Literal["stripes", "wood"], variant: int, *, short: bool = False
) -> tuple[ImageInput, TranscriptionResult]:
    """Composite a perspective card over texture, with a continuous lower-right shadow."""
    canvas = _tabletop(kind, variant)
    y, x = np.indices((420, 700), dtype=np.float64)
    shade = 244 - (20 + 8 * variant) * (x / 699) * (y / 419)
    card = Image.fromarray(shade.astype(np.uint8)).convert("RGB")
    lines = _paragraph(card, (40, 55), 30, short=short)
    transform = np.array(
        (
            (0.91, -0.12 - variant * 0.015, 390 + 12 * variant),
            (0.05 + variant * 0.02, 0.87, 290 - 8 * variant),
            (0.00008 + variant * 0.000025, -0.00007, 1),
        ),
        dtype=np.float64,
    )
    inverse = np.linalg.inv(transform)
    inverse /= inverse[2, 2]
    coefficients = tuple(float(value) for value in inverse.flat)[:8]
    layer = card.convert("RGBA").transform(
        canvas.size, Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC
    )
    canvas.paste(layer, (0, 0), layer)
    return image_and_ocr(canvas, _project_boxes(lines, transform))
