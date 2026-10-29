# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require explicit local trust and verify the unsafe development backend limits."""

import hashlib
import logging
import os
from types import SimpleNamespace

import pytest

from datakeel.core.custom_sandbox import SandboxLimits, SandboxRequest
from datakeel.core.settings import Settings
from datakeel.operators import custom_memory, custom_subprocess
from datakeel.operators.custom_sandbox import run_sandbox


@pytest.fixture
def killed_worker_groups(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Track only worker groups explicitly killed by this invocation."""
    killed: list[int] = []
    killpg = os.killpg

    def record_kill(pid: int, signum: int) -> None:
        killed.append(pid)
        killpg(pid, signum)

    monkeypatch.setattr(custom_subprocess.os, "killpg", record_kill)
    return killed


def request(
    code: str, *, trusted: bool = True, timeout: float = 2, memory: int = 64
) -> SandboxRequest:
    """Freeze a generated local development fixture."""
    return SandboxRequest(
        code=code,
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        trusted_local=trusted,
        limits=SandboxLimits(timeout_seconds=timeout, memory_mb=memory),
    )


def test_default_configuration_uses_container_and_disables_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without explicit configuration the unsafe backend is neither selected nor allowed."""
    for name in ("DATAKEEL_SANDBOX_BACKEND", "DATAKEEL_SANDBOX_ALLOW_SUBPROCESS"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.sandbox_backend == "container"
    assert settings.sandbox_allow_subprocess is False


def test_subprocess_is_disabled_by_default() -> None:
    """Configuration must opt in even for trusted local callers."""
    result = run_sandbox(
        request("def run(inputs, params, ctx): return []"), Settings(sandbox_backend="subprocess")
    )
    assert result.exit_reason == "subprocess_disabled"
    assert not result.success


def test_subprocess_refuses_external_submissions_after_opt_in() -> None:
    """A global developer setting never authorizes external submitted code."""
    result = run_sandbox(
        request("def run(inputs, params, ctx): return []", trusted=False),
        Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True),
    )
    assert result.exit_reason == "subprocess_disabled"


def test_subprocess_trusted_local_execution_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Every enabled invocation carries an explicit unsafe-development warning."""
    code = """from pathlib import Path

def run(inputs, params, ctx):
    (Path(ctx["output_dir"]) / "result").write_bytes(b"local")
    return [{"path": "result", "metadata": {}}]
"""
    with caplog.at_level(logging.WARNING):
        result = run_sandbox(
            request(code), Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True)
        )
    assert result.success, result.stderr
    assert result.outputs[0].content == b"local"
    assert "UNSAFE" in caplog.text
    assert result.backend == "subprocess"


def test_subprocess_wall_clock_limit_kills_infinite_loop() -> None:
    """An enabled trusted process still has a host-enforced deadline."""
    code = "def run(inputs, params, ctx):\n    while True: pass\n"
    result = run_sandbox(
        request(code, timeout=0.2),
        Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True),
    )
    assert result.exit_reason == "timeout"
    assert result.resources.wall_seconds < 3


def test_subprocess_memory_limit_rejects_large_allocation() -> None:
    """The real POSIX limit prevents a generated allocation beyond its memory budget."""
    code = "def run(inputs, params, ctx):\n    data = bytearray(512 * 1024 * 1024)\n    return []\n"
    result = run_sandbox(
        request(code), Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True)
    )
    assert result.exit_reason == "memory_limit", result.stderr
    assert not result.outputs


def test_subprocess_memory_limit_kills_and_reaps_owned_worker(
    killed_worker_groups: list[int],
) -> None:
    """A real over-budget worker is terminated and cannot survive the invocation."""
    code = """import time

def run(inputs, params, ctx):
    blocks = []
    for _ in range(16):
        blocks.append(bytearray(16 * 1024 * 1024))
        time.sleep(0.02)
    while True:
        time.sleep(0.01)
"""
    result = run_sandbox(
        request(code), Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True)
    )
    assert result.exit_reason == "memory_limit", result.stderr
    assert not result.success
    assert not result.outputs
    assert len(killed_worker_groups) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(killed_worker_groups[0], 0)


def test_subprocess_unreadable_native_memory_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    killed_worker_groups: list[int],
) -> None:
    """A denied monitor prevents a successful result and still cleans the worker."""

    def denied_library() -> None:
        raise PermissionError

    monkeypatch.setattr(custom_memory, "_library", denied_library)
    monkeypatch.setattr(custom_memory, "sys", SimpleNamespace(platform="darwin"))
    result = run_sandbox(
        request("import time\ndef run(inputs, params, ctx): time.sleep(1); return []"),
        Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True),
    )
    assert result.exit_reason == "runtime_error"
    assert "memory usage could not be verified" in result.stderr
    assert not result.success
    assert not result.outputs
    assert len(killed_worker_groups) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(killed_worker_groups[0], 0)


def test_subprocess_completed_worker_cleanup_denial_preserves_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing or inaccessible completed group cannot overwrite a successful result."""
    failures = iter((ProcessLookupError, PermissionError))

    def denied_kill(pid: int, signum: int) -> None:
        raise next(failures)

    monkeypatch.setattr(custom_subprocess.os, "killpg", denied_kill)
    monkeypatch.setattr(custom_subprocess, "memory_exceeded", lambda *_args: False)
    for _ in range(2):
        result = run_sandbox(
            request("def run(inputs, params, ctx): return []"),
            Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True),
        )
        assert result.success, result.stderr
        assert result.exit_reason == "completed"


def test_subprocess_repeated_short_workers_complete() -> None:
    """Repeated quick workers retain actual native monitoring through normal exit."""
    code = """from pathlib import Path

def run(inputs, params, ctx):
    (Path(ctx["output_dir"]) / "result").write_bytes(b"local")
    return [{"path": "result", "metadata": {}}]
"""
    settings = Settings(sandbox_backend="subprocess", sandbox_allow_subprocess=True)
    for attempt in range(60):
        result = run_sandbox(request(code), settings)
        assert result.success, f"attempt {attempt + 1}: {result.stderr}"
        assert result.exit_reason == "completed"
        assert len(result.outputs) == 1
        assert result.outputs[0].content == b"local"
