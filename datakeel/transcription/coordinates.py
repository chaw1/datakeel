# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate visual JSON and retain readable text when a model cannot locate a line."""

from pydantic import JsonValue, StrictFloat, ValidationError

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.models import BoundaryModel
from datakeel.core.transcription_models import OCRLine


class _VisualLine(BoundaryModel):
    text: str
    # Geometry is checked separately so malformed coordinates cannot discard visible text.
    bbox: JsonValue = None


class _VisualOutput(BoundaryModel):
    lines: tuple[_VisualLine, ...]


class _PixelRegion(ImageRegion):
    bbox: tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat]


class LocatedTranscript(BoundaryModel):
    """Return model text with only schema-validated, in-image pixel rectangles."""

    text: str
    lines: tuple[OCRLine, ...] = ()


def decode_coordinates(text: str, width: int, height: int) -> LocatedTranscript:
    """Keep legacy plain text unlocated and never substitute OCR or invented geometry."""
    try:
        output = _VisualOutput.model_validate_json(text)
    except ValidationError:
        return LocatedTranscript(text=text)
    lines: list[OCRLine] = []
    for line in output.lines:
        try:
            region = _PixelRegion.model_validate(
                {"bbox": line.bbox, "width": width, "height": height}
            )
        except ValidationError:
            continue
        lines.append(OCRLine(text=line.text, bbox=region.bbox, confidence=1))
    return LocatedTranscript(text="\n".join(line.text for line in output.lines), lines=tuple(lines))
