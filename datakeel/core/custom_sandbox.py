# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen, storage-independent requests and results for untrusted operators."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel


class SandboxLimits(BoundaryModel):
    """Bound wall time, runtime resources, and every published output."""

    timeout_seconds: float = Field(default=10, ge=0.1, le=300)
    memory_mb: int = Field(default=256, ge=32, le=2048)
    cpus: float = Field(default=1, gt=0, le=4)
    pids: int = Field(default=32, ge=8, le=128)
    max_input_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_output_files: int = Field(default=64, ge=1, le=1024)
    max_output_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_file_bytes: int = Field(default=8 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_log_bytes: int = Field(default=16384, ge=1024, le=65536)


class SandboxInput(BoundaryModel):
    """Provide only explicitly selected input bytes and JSON metadata."""

    name: str = Field(min_length=1, max_length=255)
    content: bytes
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SandboxRequest(BoundaryModel):
    """Freeze code, schemas, parameters, and limits before execution."""

    code: str = Field(max_length=131072)
    code_hash: str
    inputs: tuple[SandboxInput, ...] = Field(default=(), max_length=1024)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    parameter_schema: dict[str, JsonValue] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    metadata_schema: dict[str, JsonValue] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": False}
    )
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    trusted_local: bool = False


class SandboxOutput(BoundaryModel):
    """Carry validated bytes without trusting a container filesystem path."""

    name: str
    content: bytes
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SandboxResources(BoundaryModel):
    """Record measured wall time and available runtime accounting."""

    wall_seconds: float = 0
    cpu_seconds: float | None = None
    memory_peak_bytes: int | None = None


class SandboxResult(BoundaryModel):
    """Return no outputs on failure, with bounded diagnostics and attribution."""

    success: bool
    exit_reason: str
    backend: Literal["container", "subprocess"] = "container"
    image_digest: str = ""
    resources: SandboxResources = Field(default_factory=SandboxResources)
    outputs: tuple[SandboxOutput, ...] = ()
    stdout: str = ""
    stderr: str = ""
