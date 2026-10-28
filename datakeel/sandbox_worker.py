# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standalone user-code entry point; never imported by the platform process."""

import importlib.util
import json
import math
import resource
import sys
from pathlib import Path
from typing import Protocol, cast

type Json = str | int | float | bool | list[Json] | dict[str, Json] | None


class UserModule(Protocol):
    """Describe the single callable exported by an isolated user module."""

    def run(self, inputs: Json, params: Json, ctx: dict[str, str]) -> Json:
        """Transform selected inputs into declared output files."""
        ...


def main() -> None:
    """Load user code only in the isolated worker and write its output declaration."""
    job = Path(sys.argv[1])
    status = Path(sys.argv[2])
    request = cast("dict[str, Json]", json.loads((job / "request.json").read_text()))
    limits = request.get("resource_limits")
    if isinstance(limits, dict):
        _apply_limits(limits)
    spec = importlib.util.spec_from_file_location("custom_operator", job / "operator.py")
    if spec is None or spec.loader is None:
        msg = "Cannot load the submitted operator"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    operator = cast("UserModule", cast("object", module))
    output_dir = str(request["output_dir"])
    outputs = operator.run(request["inputs"], request["params"], {"output_dir": output_dir})
    (status / "result.json").write_text(json.dumps(outputs, allow_nan=False))


def _apply_limits(limits: dict[str, Json]) -> None:
    memory = int(str(limits["memory_mb"])) * 1024 * 1024
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_DATA, (memory, memory))
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    cpu = math.ceil(float(str(limits["timeout_seconds"]))) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    maximum = int(str(limits["max_file_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (maximum, maximum))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


if __name__ == "__main__":
    main()
