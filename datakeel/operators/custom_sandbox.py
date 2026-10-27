# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed facade for typed custom-operator sandbox execution."""

import hashlib
import json
import logging
import tempfile
import time
from pathlib import Path

from datakeel.core.custom_sandbox import SandboxRequest, SandboxResult
from datakeel.core.settings import Settings, get_settings
from datakeel.operators.custom_container import ContainerSandbox
from datakeel.operators.custom_output import OutputRejectedError, validate_schema
from datakeel.operators.custom_process import RuntimeFailureError, runtime_environment
from datakeel.operators.custom_subprocess import run_subprocess

logger = logging.getLogger(__name__)


def run_sandbox(request: SandboxRequest, settings: Settings | None = None) -> SandboxResult:
    """Execute a frozen request, publishing outputs only after every host check passes."""
    configuration = settings or get_settings()
    started = time.monotonic()
    try:
        result = _run(request, configuration)
    except OutputRejectedError as error:
        result = SandboxResult(
            success=False,
            exit_reason="invalid_output",
            backend=configuration.sandbox_backend,
            image_digest=configuration.sandbox_image,
            stderr=str(error),
        )
    except RuntimeFailureError as error:
        result = SandboxResult(
            success=False,
            exit_reason="memory_limit" if str(error) == "memory_limit" else "runtime_error",
            backend=configuration.sandbox_backend,
            image_digest=configuration.sandbox_image,
            stderr=str(error),
        )
    except OSError:
        logger.exception("Sandbox filesystem operation failed")
        result = SandboxResult(
            success=False,
            exit_reason="runtime_error",
            backend=configuration.sandbox_backend,
            image_digest=configuration.sandbox_image,
            stderr="Sandbox filesystem operation failed",
        )
    return result.model_copy(
        update={
            "resources": result.resources.model_copy(
                update={"wall_seconds": time.monotonic() - started}
            )
        }
    )


def _run(request: SandboxRequest, settings: Settings) -> SandboxResult:
    if hashlib.sha256(request.code.encode()).hexdigest() != request.code_hash:
        msg = "Code bytes do not match the approved content hash"
        raise OutputRejectedError(msg)
    for item in request.inputs:
        validate_schema({"type": "object", "additionalProperties": True}, item.metadata)
    input_size = sum(
        len(item.content) + len(json.dumps(item.metadata, allow_nan=False).encode())
        for item in request.inputs
    )
    if input_size > request.limits.max_input_bytes:
        msg = "Selected inputs exceed the sandbox byte limit"
        raise OutputRejectedError(msg)
    validate_schema(request.parameter_schema, request.params)
    if settings.sandbox_backend == "subprocess":
        if not settings.sandbox_allow_subprocess or not request.trusted_local:
            return SandboxResult(
                success=False, exit_reason="subprocess_disabled", backend="subprocess"
            )
        logger.warning("UNSAFE subprocess sandbox enabled: trusted local development code only")
        return run_subprocess(request)
    runtime = ContainerSandbox(
        settings.sandbox_image, runtime_environment(settings.sandbox_docker_host)
    )
    with tempfile.TemporaryDirectory(prefix="datakeel-sandbox-") as directory:
        return runtime.execute(request, Path(directory))
