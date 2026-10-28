# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Materialize only selected input bytes and a frozen JSON request for a sandbox."""

import json
from pathlib import Path

from datakeel.core.custom_sandbox import SandboxRequest


def write_job(request: SandboxRequest, directory: Path, output: str, *, container: bool) -> None:
    """Create read-only input snapshots without exposing any original platform path."""
    directory.mkdir(parents=True, exist_ok=True)
    inputs: list[dict[str, object]] = []
    for index, item in enumerate(request.inputs):
        filename = f"input-{index}"
        path = directory / filename
        path.write_bytes(item.content)
        path.chmod(0o444)
        inputs.append(
            {
                "path": f"/job/{filename}" if container else str(path),
                "name": item.name,
                "metadata": item.metadata,
            }
        )
    (directory / "operator.py").write_text(request.code)
    (directory / "request.json").write_text(
        json.dumps(
            {
                "inputs": inputs,
                "params": request.params,
                "output_dir": output,
                "resource_limits": None if container else request.limits.model_dump(mode="json"),
            },
            allow_nan=False,
        )
    )
    for path in directory.iterdir():
        path.chmod(0o444)
    directory.chmod(0o755)
