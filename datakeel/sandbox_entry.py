# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standalone container supervisor; user imports happen in a separate child process.

This script runs only as PID 1 of the sandbox's private PID namespace. It enforces the
execution timeout from inside the container, so user code stops at its deadline even when
the host's runtime control plane is slow. The host keeps its own independent deadline.
"""

import ctypes
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO, cast

_STATUS = Path("/status")
_RESULT_LIMIT = 65536
_PR_SET_DUMPABLE = 4


def main() -> None:
    """Run the worker, stop every user process, then keep tmpfs outputs for host validation."""
    if os.getpid() != 1:
        msg = "The sandbox supervisor must run as PID 1 of a private PID namespace"
        raise SystemExit(msg)
    protect_from_tracing()
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    log_limit = int(sys.argv[1])
    timeout = float(sys.argv[2])
    with (_STATUS / "stdout").open("wb") as stdout, (_STATUS / "stderr").open("wb") as stderr:
        code, reason = _run_worker(stdout, stderr, timeout)
        stop_all_processes()
        logs_exceeded = _truncate_logs((stdout, stderr), log_limit)
    if reason != "timeout":
        events = Path("/sys/fs/cgroup/memory.events")
        if events.is_file() and "oom_kill 0" not in events.read_text():
            reason = "memory_limit"
        if logs_exceeded:
            reason = "log_limit"
    outputs: object = []
    if reason == "completed":
        outputs, reason = declared_outputs(_STATUS / "result.json")
    publish_status({"exit_code": code, "reason": reason, "outputs": outputs})
    while True:
        time.sleep(1)


def protect_from_tracing() -> None:
    """Mark this process non-dumpable so same-UID user code cannot ptrace or patch it.

    Raises:
        SystemExit: The kernel refused the protection; the supervisor never starts user code.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        msg = "Cannot protect the sandbox supervisor from tracing"
        raise SystemExit(msg)


def _run_worker(stdout: BinaryIO, stderr: BinaryIO, timeout: float) -> tuple[int, str]:
    worker = subprocess.Popen(  # Fixed isolated interpreter and fixed script.
        [sys.executable, "-I", "/runner/worker.py", "/job", "/status"],
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    try:
        code = worker.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return -signal.SIGKILL, "timeout"
    return code, "completed" if code == 0 else "code_error"


def stop_all_processes() -> None:
    """Kill every other process in this PID namespace, including escaped descendants.

    ``kill(-1)`` from the namespace's PID 1 reaches every process in the namespace except the
    caller. The PID check makes this function refuse to run anywhere else.

    Raises:
        RuntimeError: The caller is not PID 1 of a private PID namespace.
    """
    if os.getpid() != 1:
        msg = "Refusing to signal processes outside a private sandbox PID namespace"
        raise RuntimeError(msg)
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        return
    while True:
        try:
            os.waitpid(-1, 0)
        except ChildProcessError:
            return


def _truncate_logs(streams: tuple[BinaryIO, ...], limit: int) -> bool:
    exceeded = False
    for stream in streams:
        stream.flush()
        if os.fstat(stream.fileno()).st_size >= limit:
            exceeded = True
            os.ftruncate(stream.fileno(), limit)
    return exceeded


def read_regular(path: Path, maximum: int) -> bytes | None:
    """Read a bounded regular file without following links or blocking on special files.

    Args:
        path: File written by untrusted code.
        maximum: Largest accepted size in bytes.

    Returns:
        The content, or None for a missing, linked, special or oversized file.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        content = stream.read(maximum + 1)
    return content if len(content) <= maximum else None


def declared_outputs(path: Path) -> tuple[object, str]:
    """Forward the worker's output declaration; the host validates it independently.

    Args:
        path: Declaration written after ``run`` returned.

    Returns:
        The decoded declaration and the completion reason.
    """
    if not path.is_symlink() and not path.exists():
        return [], "completed"
    content = read_regular(path, _RESULT_LIMIT)
    if content is None:
        return [], "invalid_output"
    try:
        return json.loads(content), "completed"
    except (ValueError, RecursionError):
        return [], "invalid_output"


def publish_status(state: dict[str, object], directory: Path = _STATUS) -> None:
    """Publish a complete record atomically, never replacing one the worker already wrote.

    The host validates or rejects any existing record itself. Without a readable record the
    host reaches its own deadline and reports a timeout.

    Args:
        state: Exit code, reason and forwarded output declaration.
        directory: Private status area shared with the host.
    """
    try:
        document = json.dumps(cast("object", state), allow_nan=False)
    except (ValueError, RecursionError):
        document = json.dumps({"exit_code": 0, "reason": "invalid_output", "outputs": []})
    try:
        descriptor, name = tempfile.mkstemp(dir=directory, prefix=".status-")
    except OSError:
        return
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(document)
        os.link(temporary, directory / "status.json")
    except OSError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
