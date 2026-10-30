# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One compact JSON-only instruction for boxes and/or whole-image labels."""

import json

PROMPT_VERSION = "prelabel-v1"


def prelabel_prompt(
    labels: tuple[str, ...],
    kinds: frozenset[str],
    coordinate_space: str,
    *,
    single_label: bool = False,
) -> str:
    """Ask for allowed labels only, tight boxes and a per-object probability."""
    allowed = json.dumps(list(labels), ensure_ascii=False)
    scale = (
        "integers on a 0-1000 grid relative to the image width and height"
        if coordinate_space == "normalized_1000"
        else "integer pixel coordinates of this image"
    )
    parts = [
        (
            f"You are pre-labeling one image for a dataset. Allowed labels: {allowed}. "
            "Use these strings exactly and ignore anything else."
        ),
    ]
    shape: dict[str, object] = {}
    if "box" in kinds:
        parts.append(
            'For "objects", give every visible instance of an allowed label with a tight box '
            f"[x1, y1, x2, y2] ({scale}; origin top-left, x to the right, y down) and "
            '"confidence", your probability from 0 to 1 that this label and box are correct.'
        )
        shape["objects"] = [{"label": "...", "box": [0, 0, 0, 0], "confidence": 0.0}]
    if "classification" in kinds:
        parts.append(
            'For "labels", list '
            + ("exactly one allowed label" if single_label else "the allowed labels")
            + " that describe the whole image, and give "
            '"labels_confidence", your probability from 0 to 1 that the list is correct.'
        )
        shape["labels"] = ["..."]
        shape["labels_confidence"] = 0.0
    parts.append(
        "Reply with JSON only, no prose and no code fence, shaped like "
        + json.dumps(shape, ensure_ascii=False)
        + ". Use empty lists when nothing applies."
    )
    return " ".join(parts)
