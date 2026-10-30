# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate untrusted model JSON into source-pixel boxes and labels, recording every drop.

Coordinates go through the shared P11 conversion (``to_pixels``) for the view that was sent,
are mirrored back when the view was mirrored, checked against that view's bounds, and only
then scaled to the source image. Out-of-bounds and degenerate boxes are dropped with a reason.
"""

import json
import math
from typing import NamedTuple, cast

from pydantic import JsonValue

from datakeel.core.transcription_coordinates import to_pixels
from datakeel.core.transcription_models import CoordinateSpace
from datakeel.prelabel.images import SentImage

Box = tuple[float, float, float, float]
_MIN_SIDE = 1.0


class Detection(NamedTuple):
    """One allowed-label box in source pixels with the model's own probability."""

    label: str
    box: Box
    confidence: float | None


class ParsedReply(NamedTuple):
    """Everything usable in one reply, plus what was discarded and why."""

    objects: tuple[Detection, ...]
    labels: tuple[str, ...] | None
    labels_confidence: float | None
    drops: tuple[tuple[str, str], ...]


def _document(text: str) -> dict[str, JsonValue] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value = cast("JsonValue", decoder.raw_decode(text, index)[0])
        except ValueError:
            continue
        if isinstance(value, dict) and ("objects" in value or "labels" in value):
            return value
    return None


def _probability(value: JsonValue) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return min(max(float(value), 0.0), 1.0)


def _label(value: JsonValue, lookup: dict[str, str]) -> str | None:
    return lookup.get(value.strip().casefold()) if isinstance(value, str) else None


def _coordinates(value: JsonValue) -> Box | None:
    if not isinstance(value, list) or len(value) != 4:  # noqa: PLR2004  # xyxy
        return None
    numbers = [
        item for item in value if isinstance(item, int | float) and not isinstance(item, bool)
    ]
    if len(numbers) != 4 or not all(math.isfinite(item) for item in numbers):  # noqa: PLR2004
        return None
    return (float(numbers[0]), float(numbers[1]), float(numbers[2]), float(numbers[3]))


def source_box(raw: Box, view: SentImage, space: CoordinateSpace) -> tuple[Box | None, str]:
    """Map one model box to source pixels, or return the drop reason."""
    x1, y1, x2, y2 = to_pixels(raw, view.width, view.height, space)
    if x2 <= x1 or y2 <= y1:
        return None, "degenerate"
    if x1 < 0 or y1 < 0 or x2 > view.width or y2 > view.height:
        return None, "out_of_bounds"
    if view.mirrored:
        x1, x2 = view.width - x2, view.width - x1
    scale_x = view.source_width / view.width
    scale_y = view.source_height / view.height
    box = (x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y)
    if box[2] - box[0] < _MIN_SIDE or box[3] - box[1] < _MIN_SIDE:
        return None, "degenerate"
    return box, ""


def _objects(
    rows: JsonValue, view: SentImage, lookup: dict[str, str], space: CoordinateSpace
) -> tuple[list[Detection], list[tuple[str, str]]]:
    detections: list[Detection] = []
    drops: list[tuple[str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            drops.append(("malformed", "object is not a JSON object"))
            continue
        label = _label(row.get("label"), lookup)
        coordinates = _coordinates(row.get("box"))
        if label is None:
            drops.append(("unknown_label", str(row.get("label"))[:100]))
            continue
        if coordinates is None:
            drops.append(("malformed", "box is not four finite numbers"))
            continue
        box, reason = source_box(coordinates, view, space)
        if box is None:
            drops.append((reason, json.dumps(list(coordinates))))
            continue
        detections.append(Detection(label, box, _probability(row.get("confidence"))))
    return detections, drops


def parse_reply(
    text: str, view: SentImage, lookup: dict[str, str], space: CoordinateSpace
) -> ParsedReply | None:
    """Return parsed content, or ``None`` when the reply holds no usable JSON document."""
    document = _document(text)
    if document is None:
        return None
    detections, drops = _objects(document.get("objects"), view, lookup, space)
    labels: tuple[str, ...] | None = None
    raw_labels = document.get("labels")
    if isinstance(raw_labels, list):
        known = [_label(item, lookup) for item in raw_labels]
        drops.extend(
            ("unknown_label", str(item)[:100])
            for item, value in zip(raw_labels, known, strict=True)
            if value is None
        )
        labels = tuple(dict.fromkeys(value for value in known if value is not None))
    return ParsedReply(
        tuple(detections), labels, _probability(document.get("labels_confidence")), tuple(drops)
    )
