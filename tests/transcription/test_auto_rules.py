# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise routing signals on independently drawn, offline image fixtures."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Literal

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from datakeel.core.transcription_auto import AutoRoutingConfig, OCRReference
from datakeel.core.transcription_models import OCRLine, TranscriptionResult
from datakeel.transcription.auto import decide_auto_route
from datakeel.transcription.images import normalize_image

if TYPE_CHECKING:
    from datakeel.core.transcription_models import ImageInput

FONT = ImageFont.load_default(size=22)


def _line(
    canvas: Image.Image, text: str, position: tuple[int, int], *, confidence: float = 0.98
) -> OCRLine:
    draw = ImageDraw.Draw(canvas)
    draw.text(position, text, font=FONT, fill="black")
    return OCRLine(text=text, bbox=draw.textbbox(position, text, font=FONT), confidence=confidence)


def _inputs(
    canvas: Image.Image, lines: tuple[OCRLine, ...]
) -> tuple[ImageInput, TranscriptionResult]:
    output = BytesIO()
    canvas.save(output, format="PNG")
    return normalize_image(output.getvalue()), TranscriptionResult(
        text="\n".join(line.text for line in lines),
        lines=lines,
        width=canvas.width,
        height=canvas.height,
        backend="ocr",
    )


def _document(
    text: str = "Maple Laboratory owns the current data register.", *, confidence: float = 0.98
) -> tuple[ImageInput, TranscriptionResult]:
    canvas = Image.new("RGB", (900, 380), "white")
    lines = (
        _line(canvas, text, (35, 40), confidence=confidence),
        _line(canvas, "All active entries were reviewed yesterday.", (35, 115)),
        _line(canvas, "This paragraph is ordinary printed text.", (35, 190)),
    )
    return _inputs(canvas, lines)


@pytest.mark.parametrize(
    "text",
    [
        "Maple Laboratory owns the current data register.",
        "In 2026, sales increased by 3.5 percent.",
        "A-B: ordinary punctuation; not a connector.",
        "a b c d e f g h i j k l m n o p q r s t",
        "UPPERCASE REGISTER WITH NORMAL ROW SPACING",
    ],
)
def test_clean_text_generated_document_stays_local(text: str) -> None:
    """Common typography and punctuation do not by themselves trigger vision."""
    decision = decide_auto_route(*_document(text))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)


@pytest.mark.parametrize("confidence", [0.1, 0.5, 0.84])
def test_low_confidence_below_threshold_routes_to_vision(confidence: float) -> None:
    """Weak OCR across the document is an explicit fallback reason."""
    image, result = _document()
    result = result.model_copy(
        update={
            "lines": tuple(
                line.model_copy(update={"confidence": confidence}) for line in result.lines
            )
        }
    )
    decision = decide_auto_route(image, result)
    assert decision.route == "vlm"
    assert "low_confidence" in decision.reasons


@pytest.mark.parametrize("confidence", [0.85, 0.95, 1.0])
def test_low_confidence_at_or_above_threshold_stays_local(confidence: float) -> None:
    """The documented confidence cutoff is inclusive for local routing."""
    image, result = _document()
    result = result.model_copy(
        update={
            "lines": tuple(
                line.model_copy(update={"confidence": confidence}) for line in result.lines
            )
        }
    )
    assert decide_auto_route(image, result).route == "ocr"


@pytest.mark.parametrize(
    "failure", ["exception", "error", "empty", "geometry", "whitespace", "quality", "truncated"]
)
def test_ocr_failed_missing_attempt_or_output_has_reason(failure: str) -> None:
    """A failed local attempt always permits an explainable, separately guarded fallback."""
    image, result = _document()
    if failure == "exception":
        result = None
    elif failure == "error":
        result = result.model_copy(update={"error": "ocr_not_installed"})
    elif failure == "empty":
        result = result.model_copy(update={"text": ""})
    elif failure == "geometry":
        result = result.model_copy(update={"lines": ()})
    elif failure == "quality":
        result = result.model_copy(update={"quality_issues": ("truncated",)})
    elif failure == "truncated":
        result = result.model_copy(update={"finish_reason": "length"})
    else:
        result = result.model_copy(
            update={"lines": tuple(line.model_copy(update={"text": "  "}) for line in result.lines)}
        )
    assert decide_auto_route(image, result).reasons == ("ocr_failed",)


def _diagram(
    kind: Literal["horizontal", "vertical", "diagonal", "offset", "arrow", "none", "broken"],
) -> tuple[ImageInput, TranscriptionResult]:
    canvas = Image.new("RGB", (700, 400), "white")
    left = _line(canvas, "Parent unit", (40, 55))
    positions = {
        "horizontal": (460, 55),
        "vertical": (40, 310),
        "diagonal": (460, 310),
        "offset": (40, 310),
        "arrow": (460, 55),
        "none": (460, 55),
        "broken": (460, 55),
    }
    right = _line(canvas, "Child unit", positions[kind])
    x1, y1, x2, y2 = left.bbox
    a1, b1, a2, b2 = right.bbox
    start = ((x1 + x2) / 2, (y1 + y2) / 2)
    end = ((a1 + a2) / 2, (b1 + b2) / 2)
    draw = ImageDraw.Draw(canvas)
    if kind == "offset":
        start, end = (x2 - 10, y2), (x2 - 10, b1)
    if kind not in {"none", "broken"}:
        draw.line((start, end), fill="black", width=3)
    if kind == "arrow":
        draw.polygon(((a1 - 4, end[1]), (a1 - 20, end[1] - 9), (a1 - 20, end[1] + 9)), fill="black")
    if kind == "broken":
        draw.line((x2 + 10, start[1], x2 + 30, start[1]), fill="black", width=3)
    return _inputs(canvas, (left, right))


@pytest.mark.parametrize("kind", ["horizontal", "vertical", "diagonal", "offset", "arrow"])
def test_structure_diagram_connected_labels_routes_to_vision(
    kind: Literal["horizontal", "vertical", "diagonal", "offset", "arrow"],
) -> None:
    """Connectors can be diagonal or displaced from the OCR label's centre."""
    assert "structure_diagram" in decide_auto_route(*_diagram(kind)).reasons


@pytest.mark.parametrize("kind", ["none", "broken"])
def test_structure_diagram_unconnected_labels_stay_local(
    kind: Literal["none", "broken"],
) -> None:
    """Spatially separated words and a short decoration do not imply a connection."""
    assert "structure_diagram" not in decide_auto_route(*_diagram(kind)).reasons


@pytest.mark.parametrize("arrow", ["->", "<-", "→", "⇓"])
def test_structure_diagram_ocr_recognized_arrow_remains_a_structure_signal(arrow: str) -> None:
    """Masking recognized text cannot erase the only recognized connector in a diagram."""
    canvas = Image.new("RGB", (700, 400), "white")
    lines = (
        _line(canvas, "Parent unit", (30, 40)),
        _line(canvas, arrow, (250, 40)),
        _line(canvas, "Child unit", (450, 40)),
    )
    assert "structure_diagram" in decide_auto_route(*_inputs(canvas, lines)).reasons


def test_structure_diagram_table_borders_stay_local() -> None:
    """Table grids outside the text projections are not mistaken for semantic arrows."""
    canvas = Image.new("RGB", (700, 400), "white")
    lines = tuple(
        _line(canvas, text, (x, y))
        for y in (40, 140, 240)
        for x, text in ((30, "Current owner"), (360, "Active register"))
    )
    draw = ImageDraw.Draw(canvas)
    for y in (20, 120, 220, 320):
        draw.line((10, y, 680, y), fill="black", width=2)
    for x in (10, 330, 680):
        draw.line((x, 20, x, 320), fill="black", width=2)
    decision = decide_auto_route(*_inputs(canvas, lines))
    assert "structure_diagram" not in decision.reasons


@pytest.mark.parametrize("distance", [5, 180])
def test_structure_diagram_close_or_touching_labels_do_not_imply_connector(distance: int) -> None:
    """Overlapping boxes and adjacent text columns provide no independent connecting ink."""
    canvas = Image.new("RGB", (700, 400), "white")
    first = _line(canvas, "Current register", (30, 40))
    second = _line(canvas, "Active owner", (30 + distance, 40))
    assert "structure_diagram" not in decide_auto_route(*_inputs(canvas, (first, second))).reasons


@pytest.mark.parametrize("fraction", [0.76, 0.9, 1.0])
def test_struck_rows_long_central_stroke_routes_to_vision(fraction: float) -> None:
    """A cancellation stroke inside a recognized row must not become an active fact."""
    canvas = Image.new("RGB", (700, 300), "white")
    line = _line(canvas, "Cancelled ownership of the old register", (30, 70))
    x1, y1, x2, y2 = line.bbox
    ImageDraw.Draw(canvas).line(
        (x1, (y1 + y2) / 2, x1 + (x2 - x1) * fraction, (y1 + y2) / 2), fill="black", width=2
    )
    assert "struck_or_greyed_rows" in decide_auto_route(*_inputs(canvas, (line,))).reasons


@pytest.mark.parametrize("decoration", ["underline", "above", "short"])
def test_struck_rows_ordinary_decoration_is_not_cancellation(decoration: str) -> None:
    """A heading underline or a small stroke is not a struck-through text row."""
    canvas = Image.new("RGB", (700, 300), "white")
    line = _line(canvas, "The active register belongs to Maple", (30, 70))
    x1, y1, x2, y2 = line.bbox
    y = y2 + 5 if decoration == "underline" else y1 - 5
    end = x2
    if decoration == "short":
        y, end = (y1 + y2) / 2, x1 + (x2 - x1) / 3
    ImageDraw.Draw(canvas).line((x1, y, end, y), fill="black", width=2)
    assert "struck_or_greyed_rows" not in decide_auto_route(*_inputs(canvas, (line,))).reasons


@pytest.mark.parametrize("brightness", [130, 180, 230])
def test_grey_rows_contrasting_background_routes_to_vision(brightness: int) -> None:
    """A grey row on a brighter page conveys state beyond the OCR characters."""
    canvas = Image.new("RGB", (700, 300), "white")
    ImageDraw.Draw(canvas).rectangle((15, 50, 680, 120), fill=(brightness,) * 3)
    line = _line(canvas, "Disabled ownership of the old register", (30, 70))
    assert "struck_or_greyed_rows" in decide_auto_route(*_inputs(canvas, (line,))).reasons


@pytest.mark.parametrize("brightness", [180, 230, 255])
def test_grey_rows_uniform_paper_is_not_a_disabled_row(brightness: int) -> None:
    """The rule compares row and page backgrounds instead of treating grey paper as deletion."""
    canvas = Image.new("RGB", (700, 300), (brightness,) * 3)
    line = _line(canvas, "Active ownership of the current register", (30, 70))
    assert "struck_or_greyed_rows" not in decide_auto_route(*_inputs(canvas, (line,))).reasons


def test_grey_rows_faded_text_among_dark_rows_routes_to_vision() -> None:
    """Disabled foreground text can convey cancellation even with a white row background."""
    canvas = Image.new("RGB", (700, 300), "white")
    active = _line(canvas, "Current entry is active", (30, 40))
    faded = _line(canvas, "Obsolete entry is disabled", (30, 150))
    ImageDraw.Draw(canvas).rectangle((20, 140, 680, 190), fill="white")
    ImageDraw.Draw(canvas).text((30, 150), faded.text, font=FONT, fill=(150, 150, 150))
    assert "struck_or_greyed_rows" in decide_auto_route(*_inputs(canvas, (active, faded))).reasons


def test_grey_rows_uniform_faded_text_stays_local() -> None:
    """Uniform print brightness lacks the contrasting row state needed for this signal."""
    canvas = Image.new("RGB", (700, 300), "white")
    line = _line(canvas, "The scanned document has uniform ink", (30, 40))
    ImageDraw.Draw(canvas).rectangle((20, 30, 680, 90), fill="white")
    ImageDraw.Draw(canvas).text((30, 40), line.text, font=FONT, fill=(150, 150, 150))
    assert "struck_or_greyed_rows" not in decide_auto_route(*_inputs(canvas, (line,))).reasons


def test_sparse_text_small_result_on_large_layout_routes_to_vision() -> None:
    """A few characters covering almost none of a page indicate an incomplete transcript."""
    canvas = Image.new("RGB", (2000, 2000), "white")
    line = _line(canvas, "Label", (30, 70))
    assert "sparse_text" in decide_auto_route(*_inputs(canvas, (line,))).reasons


def test_sparse_text_oversized_recognition_box_routes_to_vision() -> None:
    """Too few characters for a line's geometry indicate a recognition mismatch."""
    image, result = _document()
    line = OCRLine(text="A", bbox=(20, 20, 800, 60), confidence=0.99)
    result = result.model_copy(update={"text": "A", "lines": (line,)})
    assert "sparse_text" in decide_auto_route(image, result).reasons


def test_sparse_text_unrecognized_graphics_routes_to_vision() -> None:
    """Foreground excluded from every OCR box is a content mismatch signal."""
    canvas = Image.new("RGB", (700, 400), "white")
    line = _line(canvas, "One recognized label on a complex figure", (30, 30))
    ImageDraw.Draw(canvas).ellipse((40, 100, 650, 370), fill="black")
    assert "sparse_text" in decide_auto_route(*_inputs(canvas, (line,))).reasons


@pytest.mark.parametrize("scale", [0.5, 1, 2, 4])
def test_structure_signal_resizing_preserves_route(scale: float) -> None:
    """Geometry ratios and bounded pixel analysis support different rendering resolutions."""
    image, result = _diagram("vertical")
    with Image.open(BytesIO(image.png)) as canvas:
        resized = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)))
    lines = tuple(
        line.model_copy(update={"bbox": tuple(value * scale for value in line.bbox)})
        for line in result.lines
    )
    assert "structure_diagram" in decide_auto_route(*_inputs(resized, lines)).reasons


def test_configuration_override_and_inputs_remain_frozen() -> None:
    """A profile threshold can alter routing without mutating the supplied OCR attempt."""
    image, result = _document()
    original = result.model_dump_json()
    config = AutoRoutingConfig(min_mean_confidence=1)
    assert "low_confidence" in decide_auto_route(image, result, config).reasons
    assert result.model_dump_json() == original
    with pytest.raises(ValidationError):
        config.min_mean_confidence = 0.1  # type: ignore[misc]


def test_routing_is_deterministic_and_preserves_multiple_reasons() -> None:
    """Independent signals remain visible together and do not depend on prior runs."""
    image, result = _diagram("arrow")
    result = result.model_copy(
        update={
            "lines": tuple(line.model_copy(update={"confidence": 0.1}) for line in result.lines)
        }
    )
    decision = decide_auto_route(image, result)
    assert decision == decide_auto_route(image, result)
    assert set(decision.reasons) >= {"low_confidence", "structure_diagram"}


def test_configuration_forbids_unknown_fields_and_unversioned_policy() -> None:
    """Typos or unknown policy versions cannot silently escape the signed configuration."""
    with pytest.raises(ValidationError):
        AutoRoutingConfig.model_validate({"minimum_confidence": 0.5})
    with pytest.raises(ValidationError):
        AutoRoutingConfig.model_validate({"version": "auto-v2"})
    assert OCRReference(text="Local attempt", error="ocr_not_installed").text == "Local attempt"
