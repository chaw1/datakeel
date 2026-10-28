# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep text lines containing a caller-supplied marker in generated fixture data."""

from pathlib import Path
from typing import TypedDict

PARAMETER_SCHEMA = {
    "type": "object",
    "properties": {"contains": {"type": "string"}},
    "required": ["contains"],
    "additionalProperties": False,
}
OUTPUT_METADATA_SCHEMA = {
    "type": "object",
    "properties": {"kept_lines": {"type": "integer"}},
    "required": ["kept_lines"],
    "additionalProperties": False,
}


class Input(TypedDict):
    """One read-only input supplied by the sandbox entrypoint."""

    path: str
    name: str
    metadata: dict[str, object]


class Output(TypedDict):
    """A basename and metadata for a file written into the output directory."""

    path: str
    metadata: dict[str, object]


def run(inputs: list[Input], params: dict[str, object], ctx: dict[str, str]) -> list[Output]:
    """Filter each UTF-8 fixture and return the generated output file metadata.

    Args:
        inputs: Read-only text files selected in the pipeline manifest.
        params: A required string named ``contains``.
        ctx: Sandbox context containing its writable ``output_dir``.

    Returns:
        Generated files with the number of retained lines.
    """
    marker = str(params["contains"])
    outputs: list[Output] = []
    for index, item in enumerate(inputs):
        lines = Path(item["path"]).read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if marker in line]
        filename = f"filtered-{index}.txt"
        Path(ctx["output_dir"], filename).write_text("\n".join(kept), encoding="utf-8")
        outputs.append({"path": filename, "metadata": {"kept_lines": len(kept)}})
    return outputs
