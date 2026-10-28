# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise fail-closed request, archive, and external-command boundaries."""

import hashlib
import io
import sys
import tarfile
import time

import pytest

from datakeel.core.custom_sandbox import SandboxInput, SandboxLimits, SandboxRequest
from datakeel.core.settings import Settings, get_settings
from datakeel.operators.custom_output import (
    OutputRejectedError,
    archive_files,
    parse_status,
    validated_outputs,
)
from datakeel.operators.custom_process import (
    RuntimeFailureError,
    RuntimeOutputLimitError,
    command,
    runtime_environment,
)
from datakeel.operators.custom_sandbox import run_sandbox


def tar_entry(name: str, kind: bytes = tarfile.REGTYPE, content: bytes = b"fixture") -> bytes:
    """Generate an archive without extracting any hostile entry."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.size = len(content) if kind == tarfile.REGTYPE else 0
        archive.addfile(entry, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b/c", "a\\escape", "."])
def test_archive_unsafe_paths_are_rejected(name: str) -> None:
    """Never trust an archive path even though extraction is never performed."""
    with pytest.raises(OutputRejectedError):
        archive_files(tar_entry(name), 1024)


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE]
)
def test_archive_nonregular_entries_are_rejected(kind: bytes) -> None:
    """Links and device nodes cannot become platform artifacts."""
    with pytest.raises(OutputRejectedError):
        archive_files(tar_entry("root/file", kind), 1024)


def test_archive_invalid_or_oversized_content_is_rejected() -> None:
    """Both malformed tar and declared logical size limits fail closed."""
    for content in (b"not tar", tar_entry("root/file", content=b"xx")):
        with pytest.raises(OutputRejectedError):
            archive_files(content, 1)


def test_output_schema_rejection_is_atomic() -> None:
    """A late invalid metadata object rejects an otherwise valid first file."""
    status = parse_status(
        b'{"exit_code":0,"outputs":[{"path":"good"},{"path":"bad","metadata":{"extra":true}}]}'
    )
    with pytest.raises(OutputRejectedError):
        validated_outputs(
            {"good": b"1", "bad": b"2"}, status, SandboxRequest(code="", code_hash="")
        )


@pytest.mark.parametrize("content", [b"{}", b"invalid", b"x" * 65537])
def test_status_invalid_completion_is_rejected(content: bytes) -> None:
    """Untrusted completion records remain bounded and schema checked."""
    with pytest.raises(OutputRejectedError):
        parse_status(content)


def test_code_and_input_fingerprints_fail_before_runtime() -> None:
    """Invalid code hashes and input budgets never construct a runtime."""
    source = "def run(inputs, params, ctx): return []"
    changed = run_sandbox(SandboxRequest(code=source, code_hash="changed"), Settings())
    assert changed.exit_reason == "invalid_output"
    oversized = SandboxRequest(
        code=source,
        code_hash=hashlib.sha256(source.encode()).hexdigest(),
        inputs=(SandboxInput(name="input", content=b"too large"),),
        limits=SandboxLimits(max_input_bytes=1),
    )
    assert run_sandbox(oversized, Settings()).exit_reason == "invalid_output"


def test_container_mutable_tag_is_refused() -> None:
    """Only a content-addressed image identifier can execute approved code."""
    source = "def run(inputs, params, ctx): return []"
    request = SandboxRequest(code=source, code_hash=hashlib.sha256(source.encode()).hexdigest())
    result = run_sandbox(request, Settings(sandbox_image="datakeel-sandbox-mutable:latest"))
    assert result.exit_reason == "runtime_error"
    assert "digest" in result.stderr


def test_runtime_environment_has_only_explicit_allowlist() -> None:
    """No application or provider environment variable reaches the external runtime."""
    assert set(runtime_environment()) == {"PATH", "LANG"}
    assert set(runtime_environment("unix:///example.sock")) == {"PATH", "LANG", "DOCKER_HOST"}


def test_runtime_command_output_and_time_are_bounded() -> None:
    """A broken external executable cannot grow host capture buffers or run forever."""
    environment = runtime_environment()
    with pytest.raises(RuntimeOutputLimitError, match="byte limit"):
        command(
            [sys.executable, "-I", "-c", "import os; os.write(1, b'x' * 4096)"],
            environment,
            maximum=1024,
        )
    with pytest.raises(RuntimeFailureError, match="timed out"):
        command(
            [sys.executable, "-I", "-c", "import time; time.sleep(5)"], environment, timeout=0.05
        )
    with pytest.raises(RuntimeFailureError):
        command(["/nonexistent-runtime-fixture"], environment)


def test_docker_host_alias_is_refreshed_and_prefixed_setting_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single settings boundary supports Docker's alias without a stale cache."""
    monkeypatch.delenv("DATAKEEL_SANDBOX_DOCKER_HOST", raising=False)
    monkeypatch.setenv("DOCKER_HOST", "unix:///first.sock")
    assert get_settings().sandbox_docker_host == "unix:///first.sock"
    monkeypatch.setenv("DOCKER_HOST", "unix:///second.sock")
    assert get_settings().sandbox_docker_host == "unix:///second.sock"
    monkeypatch.setenv("DATAKEEL_SANDBOX_DOCKER_HOST", "unix:///preferred.sock")
    assert get_settings().sandbox_docker_host == "unix:///preferred.sock"


def test_runtime_command_closed_pipes_still_obeys_deadline() -> None:
    """Closing both pipes cannot hide an external executable that remains running."""
    source = "import os,time; os.close(1); os.close(2); time.sleep(5)"
    started = time.monotonic()
    with pytest.raises(RuntimeFailureError, match="timed out"):
        command([sys.executable, "-I", "-c", source], runtime_environment(), timeout=0.05)
    assert time.monotonic() - started < 1
