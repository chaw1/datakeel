# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise grounding, repeated text, sparse OCR and orientation-correct metadata stripping."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import OCRLine, TranscriptionResult
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.alignment import align_regions, match_box, normalize
from datakeel.transcription.images import normalize_image
from datakeel.transcription.ocr import quadrilateral_box
from datakeel.transcription.quality import checked_transcribe, quality_issues

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput


def _line(text: str, y: float = 1, x: float = 1) -> OCRLine:
    return OCRLine(text=text, bbox=(x, y, x + 30, y + 10), confidence=0.9)


@pytest.mark.parametrize("evidence", ["Alpha", "`ALPHA`", "\uff21\uff4c\uff50\uff48\uff41"])
def test_alignment_when_exact_or_normalized_matches(evidence: str) -> None:
    """Whitespace, markdown and full-width text normalize before exact lookup."""
    assert match_box(evidence, (_line("Alpha"),), 100, 100) == (1, 1, 31, 11)
    assert normalize(" **A l p h a** ") == "alpha"


def test_alignment_when_fuzzy_and_cross_line_preserves_enclosing_geometry() -> None:
    """Accept an isolated OCR substitution and exact evidence spanning adjacent lines."""
    assert match_box("Alphx", (_line("Alpha"),), 100, 100) is not None
    assert match_box("Alpha Beta", (_line("Alpha"), _line("Beta", 20)), 100, 100) == (1, 1, 31, 30)
    assert match_box(
        "Alpha Beta", (_line("Alpha"), _line("Other", 20), _line("Beta", 40)), 100, 100
    ) == (1, 1, 31, 50)


@pytest.mark.parametrize("separator", ["-->", "→", "--", "|", "...", "\n"])
def test_alignment_when_fragments_match_keeps_multiple_regions(separator: str) -> None:
    """Preserve separate arrow/table fragments for product evidence instead of one huge box."""
    regions = align_regions(
        f"Alpha {separator} Beta", (_line("Alpha"), _line("Beta", 30)), 100, 100
    )
    assert len(regions) == 2
    assert match_box(f"Alpha {separator} Beta", (_line("Alpha"), _line("Beta", 30)), 100, 100) == (
        1,
        1,
        31,
        40,
    )


def test_alignment_when_repeated_uses_occurrence_nearest_rarest_fragment() -> None:
    """A unique tail anchors the correct nearby repeated head."""
    lines = (_line("Alpha", 1), _line("Alpha", 70), _line("Beta", 60))
    assert match_box("Alpha --> Beta", lines, 100, 100) == (1, 60, 31, 80)
    assert align_regions("X --> : --> unmatched", lines, 100, 100) == ()
    assert match_box("", lines, 100, 100) is None
    assert match_box("Alpha", (), 100, 100) is None


def test_alignment_when_fuzzy_multiword_fallback_and_image_edge_matches() -> None:
    """Use whole-fragment fuzzy matching after a word cannot match exactly."""
    assert match_box("Alphx Beta", (_line("Alpha Beta"),), 100, 100) is not None
    assert match_box("xAlpha", (_line("Alpha"),), 100, 100) is not None
    assert match_box("prefixAlphasuffix", (_line("Alpha"),), 100, 100) == (1, 1, 31, 11)
    assert match_box("longUnmatchedQuote", (_line("Beta"),), 100, 100) is None


def test_geometry_when_rotated_or_out_of_bounds_encloses_then_validates() -> None:
    """Do not clip or silently accept OCR boxes outside corrected source dimensions."""
    assert quadrilateral_box(((10, 1), (21, 5), (15, 20), (1, 12))) == (1, 1, 21, 20)
    with pytest.raises(ValidationError, match="four corners"):
        quadrilateral_box(((1, 2),))
    with pytest.raises(ModelValidationError, match="within the image"):
        TranscriptionResult(
            text="Alpha", lines=(_line("Alpha", x=90),), width=100, height=100, backend="ocr"
        )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"text": " **  "}, "empty"),
        ({"finish_reason": "length"}, "truncated"),
        ({"text": "Alpha\nAlpha\nAlpha"}, "repeated"),
        ({"text": "abcdefgh" * 4}, "repeated"),
        ({"error": "timeout"}, "timeout"),
        ({"error": "http_500"}, "provider_error"),
    ],
)
def test_quality_when_bad_output_fails_explicitly_and_retains_usage(
    image_input: ImageInput,
    transcription_result: TranscriptionResult,
    change: dict[str, object],
    expected: str,
) -> None:
    """Every quality category becomes an actionable failure after observed usage is retained."""
    result = transcription_result.model_copy(update={**change, "output_tokens": 17})
    with pytest.raises(TranscriptionFailure) as captured:
        checked_transcribe(FakeTranscriber((result,)), image_input)
    assert captured.value.reason == expected
    assert captured.value.result.output_tokens == 17


def test_quality_when_ocr_sparse_allows_normal_visual_transcription(
    image_input: ImageInput, transcription_result: TranscriptionResult
) -> None:
    """Empty OCR must not create a spurious length-ratio failure for legible VLM output."""
    result = transcription_result.model_copy(update={"lines": (), "backend": "vlm"})
    assert checked_transcribe(FakeTranscriber((result,)), image_input) == result
    result = result.model_copy(update={"text": "one normal paragraph with many distinct words"})
    assert quality_issues(result) == ()
    result = result.model_copy(update={"text": "| --- |\n| --- |\n| --- |"})
    assert quality_issues(result) == ()


def test_quality_when_ocr_long_enforces_two_and_half_ratio(
    transcription_result: TranscriptionResult,
) -> None:
    """Apply the ratio only once normalized OCR reaches the declared minimum length."""
    text = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHJKL"
    result = transcription_result.model_copy(
        update={"text": text, "lines": (_line("abcdefghijklmnopqrs"),)}
    )
    assert quality_issues(result) == ()
    result = result.model_copy(
        update={"text": text + "MNOPQR", "lines": (_line("abcdefghijklmnopqrst"),)}
    )
    assert quality_issues(result) == ("repeated",)


def test_image_when_exif_rotated_transposes_and_removes_all_metadata() -> None:
    """Coordinate dimensions follow displayed pixels and no source metadata crosses transport."""
    source = Image.new("RGB", (30, 10), "white")
    exif = Image.Exif()
    exif[274], exif[270] = 6, "private-description"
    content = BytesIO()
    source.save(content, format="JPEG", exif=exif)
    normalized = normalize_image(content.getvalue())
    assert (normalized.width, normalized.height) == (10, 30)
    assert b"private-description" not in normalized.png
    with Image.open(BytesIO(normalized.png)) as decoded:
        assert not decoded.getexif()
        assert decoded.info == {}
    with pytest.raises(ValidationError, match="decoded"):
        normalize_image(b"not an image")
