# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate untrusted visual wire output at a frozen, pixel-coordinate boundary."""

import json
from typing import Self, cast

from pydantic import ConfigDict, JsonValue, StrictFloat, ValidationError

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.models import BoundaryModel
from datakeel.core.transcription_models import CoordinateSpace, OCRLine, TranscriptionIssue


class _VisualLine(BoundaryModel):
    # Model wire output may include harmless annotations; internal boundaries stay strict.
    model_config = ConfigDict(extra="ignore", frozen=True)
    text: str
    bbox: JsonValue = None


class _Box(BoundaryModel):
    bbox: tuple[StrictFloat, StrictFloat, StrictFloat, StrictFloat]


def to_pixels(
    bbox: tuple[float, float, float, float],
    width: int,
    height: int,
    coordinate_space: CoordinateSpace = "pixel",
) -> tuple[float, float, float, float]:
    """Convert model xyxy output to pixels of the image the model was sent."""
    if coordinate_space == "pixel":
        return bbox
    divisor = 1000 if coordinate_space == "normalized_1000" else 1
    x1, y1, x2, y2 = bbox
    return (
        x1 / divisor * width,
        y1 / divisor * height,
        x2 / divisor * width,
        y2 / divisor * height,
    )


def _rows(text: str) -> list[JsonValue]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value = cast("JsonValue", decoder.raw_decode(text, index)[0])
        except ValueError:
            continue
        rows = value.get("lines") if isinstance(value, dict) else value
        if isinstance(rows, list) and any(
            isinstance(row, dict) and isinstance(row.get("text"), str) for row in rows
        ):
            return rows
    return []


class LocatedTranscript(BoundaryModel):
    """Expose only parsed line text, validated geometry and safe diagnostic counts."""

    text: str
    lines: tuple[OCRLine, ...] = ()
    quality_issues: tuple[TranscriptionIssue, ...] = ()
    ignored_field_count: int = 0

    @classmethod
    def decode(
        cls, text: str, width: int, height: int, coordinate_space: CoordinateSpace = "pixel"
    ) -> Self:
        """Strip wire wrappers and isolate malformed lines without leaking a JSON envelope."""
        words: list[str] = []
        lines: list[OCRLine] = []
        ignored = 0
        for row in _rows(text):
            try:
                line = _VisualLine.model_validate(row)
            except ValidationError:
                continue
            words.append(line.text)
            ignored += len(set(row) - {"text", "bbox"}) if isinstance(row, dict) else 0
            try:
                bbox = _Box.model_validate({"bbox": line.bbox}).bbox
                region = ImageRegion.model_validate(
                    {
                        "bbox": to_pixels(bbox, width, height, coordinate_space),
                        "width": width,
                        "height": height,
                    }
                )
            except ValidationError:
                continue
            lines.append(OCRLine(text=line.text, bbox=region.bbox, confidence=1))
        return cls(
            text="\n".join(words),
            lines=tuple(lines),
            ignored_field_count=ignored,
            quality_issues=() if words else ("unparseable_structured_output",),
        )
