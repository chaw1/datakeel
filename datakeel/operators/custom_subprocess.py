# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicitly unsafe local-development execution with basic POSIX resource limits."""

import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from datakeel.core.custom_sandbox import SandboxLimits, SandboxRequest, SandboxResult
from datakeel.operators.custom_job import write_job
from datakeel.operators.custom_output import (
    OutputRejectedError,
    WorkerStatus,
    parse_status,
    validated_outputs,
)
from datakeel.operators.custom_process import command, runner_path, runtime_environment

_MAXIMUM_STATUS = 65536


def run_subprocess(request: SandboxRequest) -> SandboxResult:
    """Execute only trusted local code; these limits do not provide a security boundary."""
    with tempfile.TemporaryDirectory(prefix="datakeel-sandbox-") as temporary:
        root = Path(temporary)
        output, status, job = root / "output", root / "status", root / "job"
        output.mkdir()
        status.mkdir()
        write_job(request, job, str(output), container=False)
        return _execute(request, job, output, status)


def _execute(request: SandboxRequest, job: Path, output: Path, status: Path) -> SandboxResult:
    with (
        (status / "stdout").open("wb") as stdout,
        (status / "stderr").open("wb") as stderr,
        subprocess.Popen(  # noqa: S603  # Explicit trusted local opt-in; no shell or secrets.
            [sys.executable, "-I", str(runner_path("sandbox_worker.py")), str(job), str(status)],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=runtime_environment(),
            start_new_session=True,
        ) as process,
    ):
        try:
            reason = _wait(process, request, output, status)
        finally:
            _kill_group(process.pid)
    logs = {
        name: (status / name).read_bytes()[: request.limits.max_log_bytes].decode(errors="ignore")
        for name in ("stdout", "stderr")
    }
    if not reason and process.returncode:
        reason = "memory_limit" if "MemoryError" in logs["stderr"] else "code_error"
    if reason:
        return SandboxResult(
            success=False,
            exit_reason=reason,
            backend="subprocess",
            stdout=logs["stdout"],
            stderr=logs["stderr"],
        )
    worker_status = _status(status)
    files = _local_files(output, request.limits)
    return SandboxResult(
        success=True,
        exit_reason="completed",
        backend="subprocess",
        outputs=validated_outputs(files, worker_status, request),
        stdout=logs["stdout"],
        stderr=logs["stderr"],
    )


def _wait(
    process: subprocess.Popen[bytes], request: SandboxRequest, output: Path, status: Path
) -> str:
    deadline = time.monotonic() + request.limits.timeout_seconds
    while process.poll() is None:
        if time.monotonic() >= deadline:
            return "timeout"
        if _memory_exceeded(process.pid, request.limits.memory_mb):
            return "memory_limit"
        if any(
            (status / name).stat().st_size > request.limits.max_log_bytes
            for name in ("stdout", "stderr")
        ):
            return "log_limit"
        if sum(path.lstat().st_size for path in output.iterdir()) > request.limits.max_output_bytes:
            return "output_limit"
        time.sleep(0.01)
    return ""


def _memory_exceeded(pid: int, memory_mb: int) -> bool:
    if sys.platform != "darwin":
        return False
    measured = command(
        ["/bin/ps", "-o", "rss=", "-p", str(pid)], runtime_environment(), timeout=1, maximum=1024
    )
    return not measured.code and int(measured.stdout.strip() or b"0") > memory_mb * 1024


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _status(directory: Path) -> WorkerStatus:
    result = directory / "result.json"
    if not result.is_file() or result.stat().st_size > _MAXIMUM_STATUS:
        msg = "Missing or oversized output manifest"
        raise OutputRejectedError(msg)
    return parse_status(
        json.dumps({"exit_code": 0, "outputs": json.loads(result.read_text())}).encode()
    )


def _local_files(directory: Path, limits: SandboxLimits) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in directory.iterdir():
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            msg = "Output links, directories, and special files are forbidden"
            raise OutputRejectedError(msg)
        if details.st_size > limits.max_file_bytes:
            msg = "Output file exceeds the per-file limit"
            raise OutputRejectedError(msg)
        files[path.name] = path.read_bytes()
    return files
