# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject invalid native measurements without inspecting unrelated processes."""

import ctypes
import struct
import subprocess
from types import SimpleNamespace
from typing import cast

import pytest

from datakeel.operators import custom_memory
from datakeel.operators.custom_process import RuntimeFailureError


def _live_worker() -> subprocess.Popen[bytes]:
    def wait(timeout: float) -> int:
        command = "owned-worker"
        raise subprocess.TimeoutExpired(command, timeout)

    return cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123, poll=lambda: None, wait=wait))


@pytest.mark.parametrize(("resident", "expected"), [(64 * 1024 * 1024, False), (67108865, True)])
def test_native_memory_measurement_uses_owned_pid_and_byte_limit(
    monkeypatch: pytest.MonkeyPatch, resident: int, *, expected: bool
) -> None:
    """Native resident bytes are compared with the configured binary megabyte budget."""
    process = _live_worker()

    def measure(pid: int, flavor: int, argument: int, buffer: ctypes.c_void_p, size: int) -> int:
        assert (pid, flavor, argument, size) == (123, 4, 0, 96)
        ctypes.memmove(buffer, struct.pack("=QQ", 1, resident), 16)
        return 96

    library = SimpleNamespace(proc_pidinfo=measure)
    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", lambda: library)
    assert custom_memory.memory_exceeded(process, 64) is expected


@pytest.mark.parametrize("returned", [0, -1, 95, 97])
def test_live_worker_incomplete_native_measurement_is_rejected(
    monkeypatch: pytest.MonkeyPatch, returned: int
) -> None:
    """The native API must return exactly the SDK structure's complete size."""
    process = _live_worker()
    library = SimpleNamespace(proc_pidinfo=lambda *_args: returned)
    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", lambda: library)
    with pytest.raises(RuntimeFailureError, match="could not be verified"):
        custom_memory.memory_exceeded(process, 64)


def test_live_worker_zero_native_resident_memory_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete zero-filled native result cannot silently disable the limit."""
    process = _live_worker()
    library = SimpleNamespace(proc_pidinfo=lambda *_args: 96)
    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", lambda: library)
    with pytest.raises(RuntimeFailureError, match="could not be verified"):
        custom_memory.memory_exceeded(process, 64)


def test_worker_exit_during_native_measurement_is_not_monitor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An already reaped child no longer needs a live-process memory measurement."""
    process = cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123, poll=lambda: 0))
    library = SimpleNamespace(proc_pidinfo=lambda *_args: 0)
    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", lambda: library)
    assert not custom_memory.memory_exceeded(process, 64)


def test_worker_exit_during_native_exception_is_not_monitor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native failures observed after child exit do not reject a completed worker."""
    failures = iter((AttributeError, PermissionError, ProcessLookupError) * 2)

    def denied_library() -> None:
        raise next(failures)

    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", denied_library)
    for returncode in (0, None):
        process = cast(
            "subprocess.Popen[bytes]",
            SimpleNamespace(pid=123, poll=lambda code=returncode: code, wait=lambda **_kwargs: 0),
        )
        for _ in range(3):
            failure = None
            exceeded = True
            try:
                exceeded = custom_memory.memory_exceeded(process, 64)
            except RuntimeFailureError as error:
                failure = error
            assert failure is None, str(failure)
            assert not exceeded


def test_live_worker_native_exception_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker still alive after the bounded exit wait cannot bypass native monitoring."""
    process = _live_worker()
    failures = iter((AttributeError, PermissionError, ProcessLookupError))

    def denied_library() -> None:
        raise next(failures)

    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(custom_memory, "_library", denied_library)
    for _ in range(3):
        failure = None
        exceeded = None
        try:
            exceeded = custom_memory.memory_exceeded(process, 64)
        except RuntimeFailureError as error:
            failure = error
        assert isinstance(failure, RuntimeFailureError)
        assert "could not be verified" in str(failure)
        assert exceeded is None


def test_other_posix_hosts_keep_worker_resource_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The native Darwin monitor is not loaded on hosts using worker POSIX limits."""
    process = cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123))

    def forbidden_library() -> None:
        pytest.fail("Darwin native API must not be loaded on another platform")

    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(custom_memory, "_library", forbidden_library)
    assert not custom_memory.memory_exceeded(process, 64)
