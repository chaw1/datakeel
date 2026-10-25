# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep ordinary document formatting and transparent source pixels intact."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from datakeel.core.transcription_models import TranscriptionResult
from datakeel.transcription.images import normalize_image
from datakeel.transcription.ocr import RapidOCRTranscriber
from datakeel.transcription.quality import quality_issues

if TYPE_CHECKING:
    import numpy as np


@pytest.mark.parametrize(
    "text",
    [
        (
            "| A | B | C | D | E | F | G | H |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| one | two | three | four | five | six | seven | eight |"
        ),
        "Name: ________________________________________\nDepartment: ____________",
        (
            "Introduction ................................ 1\n"
            "Overview ................................ 2"
        ),
        "Introduction …………………………………………………… 1\nOverview ———————————————— 2",
        "Section -------------------------------------- end",
        "……\n……\n……",
        "\u59d3\u540d\uff1a________\n" * 3,
        "Signature ____ Date ____\n" * 3,
        "| 项目 | 结果 |\n| --- | --- |\n" + "| 合格 | 合格 |\n" * 3,
    ],
)
def test_visual_quality_when_document_has_formatting_accepts(text: str) -> None:
    """Tables and blank fields are formatting, not generated narrative loops."""
    result = TranscriptionResult(text=text, width=200, height=100, backend="vlm", mode="vlm")
    assert quality_issues(result) == ()


def test_ocr_quality_when_cells_repeat_accepts(transcription_result: TranscriptionResult) -> None:
    """Independent OCR cells and repeated printed paragraphs are valid source observations."""
    for text in ("通过\n通过\n通过", "abcdefgh" * 4):
        assert quality_issues(transcription_result.model_copy(update={"text": text})) == ()


def test_visual_quality_when_narrative_repeats_still_rejects(
    transcription_result: TranscriptionResult,
) -> None:
    """Stripping decorative characters cannot hide genuine repeated model output."""
    result = transcription_result.model_copy(
        update={"text": "A repeated sentence.\n" * 3, "mode": "vlm"}
    )
    assert quality_issues(result) == ("repeated",)


@pytest.mark.parametrize("text", ["| 合格 | 合格 |\n" * 8, "\u59d3\u540d\uff1a\n" * 8])
def test_visual_quality_when_short_rows_loop_rejects(
    transcription_result: TranscriptionResult, text: str
) -> None:
    """Long runs of identical table rows or labels still count as a model loop."""
    result = transcription_result.model_copy(update={"text": text, "mode": "vlm"})
    assert quality_issues(result) == ("repeated",)


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_transparent_image_when_normalized_ocr_receives_white_background(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transparent black pixels composite onto white for corrected images and OCR arrays."""
    source = Image.new("RGBA", (20, 10), (0, 0, 0, 0))
    source.putpixel((2, 2), (0, 0, 0, 255))
    converted = source.convert(mode)
    content = BytesIO()
    converted.save(content, format="PNG")
    normalized = normalize_image(content.getvalue())
    with Image.open(BytesIO(normalized.png)) as clean:
        assert clean.getpixel((0, 0)) == (255, 255, 255)
        assert clean.getpixel((2, 2)) == (0, 0, 0)

    def engine(pixels: np.ndarray[tuple[int, ...], np.dtype[np.uint8]]) -> object:
        assert tuple(pixels[0, 0]) == (255, 255, 255)
        assert tuple(pixels[2, 2]) == (0, 0, 0)
        return SimpleNamespace(boxes=None, txts=None, scores=None)

    monkeypatch.setattr(
        "datakeel.transcription.ocr.import_module",
        lambda _: SimpleNamespace(disable_telemetry_events=lambda: None, RapidOCR=lambda: engine),
    )
    assert RapidOCRTranscriber().transcribe(normalized).width == 20
