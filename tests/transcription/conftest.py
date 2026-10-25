# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate isolated pixels and typed output without loading any real OCR or model."""

from io import BytesIO

import pytest
from PIL import Image

from datakeel.core.transcription_models import ImageInput, OCRLine, TranscriptionResult
from datakeel.transcription.images import normalize_image


@pytest.fixture
def image_input() -> ImageInput:
    """Create a tiny local PNG with no source dataset or model dependency."""
    content = BytesIO()
    Image.new("RGB", (120, 80), "white").save(content, format="PNG")
    return normalize_image(content.getvalue())


@pytest.fixture
def transcription_result() -> TranscriptionResult:
    """Provide normal text and one in-bounds OCR line."""
    return TranscriptionResult(
        text="Alpha owns Beta.",
        lines=(OCRLine(text="Alpha owns Beta.", bbox=(1, 2, 90, 20), confidence=0.95),),
        width=120,
        height=80,
        backend="ocr",
        model="fixture",
    )
