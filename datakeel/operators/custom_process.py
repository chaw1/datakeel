# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound external runtime commands and expose no inherited application environment."""

import os
import selectors
import subprocess
import time
from pathlib import Path

from datakeel.core.errors import DatakeelError
from datakeel.core.models import BoundaryModel


class CommandResult(BoundaryModel):
    """Collect a bounded external command result."""

    code: int
    stdout: bytes = b""
    stderr: bytes = b""


class RuntimeFailureError(DatakeelError):
    """Report an unavailable or unresponsive container runtime."""


class RuntimeOutputLimitError(RuntimeFailureError):
    """Report command output that exceeded its bounded capture buffer."""


def command(
    arguments: list[str], environment: dict[str, str], timeout: float = 10, maximum: int = 65536
) -> CommandResult:
    """Run literal arguments, bounding both pipe output and the command lifetime."""
    try:
        with subprocess.Popen(  # noqa: S603  # Literal arguments; no shell or inherited secrets.
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        ) as process:
            return _collect(process, timeout, maximum)
    except (OSError, subprocess.SubprocessError) as error:
        msg = "Container runtime command failed or timed out"
        raise RuntimeFailureError(msg) from error


def _collect(process: subprocess.Popen[bytes], timeout: float, maximum: int) -> CommandResult:
    streams = (process.stdout, process.stderr)
    if any(stream is None for stream in streams):
        msg = "Runtime pipes are unavailable"
        raise RuntimeFailureError(msg)
    collected: dict[int, bytearray] = {0: bytearray(), 1: bytearray()}
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        for index, stream in enumerate(streams):
            if stream is not None:
                selector.register(stream, selectors.EVENT_READ, index)
        while selector.get_map():
            if time.monotonic() >= deadline:
                process.kill()
                msg = "Container runtime command timed out"
                raise RuntimeFailureError(msg)
            for key, _mask in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                block = os.read(key.fd, 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                collected[key.data].extend(block)
                if sum(map(len, collected.values())) > maximum:
                    process.kill()
                    msg = "Container runtime output exceeds the byte limit"
                    raise RuntimeOutputLimitError(msg)
    try:
        code = process.wait(timeout=max(0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as error:
        process.kill()
        msg = "Container runtime command timed out"
        raise RuntimeFailureError(msg) from error
    return CommandResult(code=code, stdout=bytes(collected[0]), stderr=bytes(collected[1]))


def runtime_environment(docker_host: str | None = None) -> dict[str, str]:
    """Construct an explicit environment without provider keys, proxy, or user configuration."""
    environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
    if docker_host:
        environment["DOCKER_HOST"] = docker_host
    return environment


def runner_path(name: str) -> Path:
    """Locate a standalone script without importing it into the platform process."""
    return Path(__file__).resolve().parents[1] / name
