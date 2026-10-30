# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score each model object by whether an independent mirrored pass finds it again.

The second request sends the left-right mirrored image; its boxes are mapped back to source
pixels and matched to the first pass one-to-one under the same label by descending IoU, like
P11's OCR cross-check. An object's agreement is that IoU (0 when unmatched).
"""

from collections.abc import Sequence
from typing import Literal

Box = tuple[float, float, float, float]
ConfidenceSource = Literal["self", "cross_check", "combined"]
_UNKNOWN_SELF = 0.5


def tuple_iou(first: Box, second: Box) -> float:
    """Compute xyxy IoU of two finite boxes."""
    width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    intersection = width * height
    union = (
        (first[2] - first[0]) * (first[3] - first[1])
        + (second[2] - second[0]) * (second[3] - second[1])
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def agreements(
    primary: Sequence[tuple[str, Box]], mirrored: Sequence[tuple[str, Box]]
) -> tuple[float, ...]:
    """Return, per primary object, the IoU of its one-to-one same-label mirrored match."""
    candidates = sorted(
        (
            (tuple_iou(left[1], right[1]), i, j)
            for i, left in enumerate(primary)
            for j, right in enumerate(mirrored)
            if left[0] == right[0]
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    result = [0.0] * len(primary)
    used: set[int] = set()
    for score, i, j in candidates:
        if score <= 0 or result[i] > 0 or j in used:
            continue
        result[i] = score
        used.add(j)
    return tuple(result)


def object_confidence(
    reported: float | None, agreement: float | None, source: ConfidenceSource
) -> float:
    """Combine the model's own probability with cross-check agreement per configured source."""
    own = _UNKNOWN_SELF if reported is None else reported
    if source == "self" or agreement is None:
        return round(own, 6)
    if source == "cross_check":
        return round(agreement, 6)
    return round((own + agreement) / 2, 6)
