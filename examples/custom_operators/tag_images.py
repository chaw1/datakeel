# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize generated image fixtures and attach a caller-supplied label."""

from pathlib import Path
from typing import TypedDict

from PIL import Image

PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
    "additionalProperties": False,
}
OUTPUT_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
    },
    "required": ["label", "width", "height"],
    "additionalProperties": False,
}


class Input(TypedDict):
    """One read-only image supplied by the sandbox entrypoint."""

    path: str
    name: str
    metadata: dict[str, object]


class Output(TypedDict):
    """A generated image basename and its validated metadata."""

    path: str
    metadata: dict[str, object]


def run(inputs: list[Input], params: dict[str, object], ctx: dict[str, str]) -> list[Output]:
    """Save clean RGB images and record the requested label and dimensions.

    Args:
        inputs: Read-only image files selected in the pipeline manifest.
        params: A required string named ``label``.
        ctx: Sandbox context containing its writable ``output_dir``.

    Returns:
        Generated PNG files with label and dimensions.
    """
    outputs: list[Output] = []
    for index, item in enumerate(inputs):
        filename = f"tagged-{index}.png"
        with Image.open(item["path"]) as image:
            normalized = image.convert("RGB")
            normalized.save(Path(ctx["output_dir"], filename), format="PNG")
            metadata: dict[str, object] = {
                "label": str(params["label"]),
                "width": normalized.width,
                "height": normalized.height,
            }
        outputs.append({"path": filename, "metadata": metadata})
    return outputs
