# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retain independently measured resources when rejecting untrusted outputs."""

import io
import tarfile
import time
from pathlib import Path

import pytest

from datakeel.core.custom_sandbox import SandboxLimits, SandboxRequest
from datakeel.operators.custom_container import ContainerSandbox, ContainerUsage
from datakeel.operators.custom_output import OutputRejectedError, WorkerStatus
from datakeel.operators.custom_process import (
    CommandResult,
    RuntimeFailureError,
    RuntimeOutputLimitError,
)


@pytest.mark.parametrize(("oom", "reason"), [(0, "invalid_output"), (1, "memory_limit")])
def test_output_rejection_retains_kernel_resource_measurements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, oom: int, reason: str
) -> None:
    """Output validation failures preserve measured CPU/peak memory and real OOM attribution."""
    runtime = object.__new__(ContainerSandbox)
    runtime.digest = "sha256:" + "a" * 64
    runtime.name = "datakeel-sandbox-fixture"
    usage = ContainerUsage(events=f"oom_kill {oom}\n", peak="123456\n", cpu="usage_usec 12000\n")
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "verify_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "arguments", lambda _request, _directory: [])
    monkeypatch.setattr(runtime, "call", lambda *_arguments, **_kwargs: CommandResult(code=0))
    monkeypatch.setattr(runtime, "wait", lambda _request: WorkerStatus(exit_code=0))
    monkeypatch.setattr(runtime, "usage", lambda _deadline: usage)
    monkeypatch.setattr(runtime, "cleanup", lambda: None)

    def reject_output(request: SandboxRequest, status: WorkerStatus) -> None:
        msg = "Invalid output metadata"
        raise OutputRejectedError(msg)

    monkeypatch.setattr(runtime, "collect", reject_output)
    result = runtime.execute(SandboxRequest(code="", code_hash=""), tmp_path)
    assert not result.success
    assert result.exit_reason == reason
    assert not result.outputs
    assert result.resources.cpu_seconds == 0.012
    assert result.resources.memory_peak_bytes == 123456
    assert result.image_digest == runtime.digest


def _runtime() -> ContainerSandbox:
    runtime = object.__new__(ContainerSandbox)
    runtime.name = "datakeel-sandbox-uncertain-fixture"
    runtime.digest = "sha256:" + "a" * 64
    runtime.image = runtime.digest
    runtime.container_attempted = False
    runtime.container_created = False
    runtime.attempted_volumes = []
    return runtime


@pytest.mark.parametrize("phase", ["container", "volume"])
def test_create_client_timeout_cleans_resources_created_by_daemon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """A disconnected create client cannot hide resources already created by the daemon."""
    runtime = _runtime()
    owners: dict[str, str] = {}
    removed: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        if arguments[:2] == ("volume", "inspect"):
            return CommandResult(code=1)
        if arguments[:2] == ("volume", "create"):
            owners[arguments[-1]] = runtime.name
            if phase == "volume":
                msg = "Container runtime command timed out"
                raise RuntimeFailureError(msg)
        elif arguments[0] == "inspect":
            return CommandResult(code=0, stdout=runtime.name.encode())
        elif arguments[0] == "create":
            owners[runtime.name] = runtime.name
            msg = "Container runtime command timed out"
            raise RuntimeFailureError(msg)
        elif arguments[:2] == ("volume", "rm") or arguments[0] == "rm":
            removed.append(arguments[-1])
            owners.pop(arguments[-1])
        return CommandResult(code=0)

    monkeypatch.setattr(runtime, "call", call)
    monkeypatch.setattr(runtime, "owned", lambda _resource, name: owners.get(name) == runtime.name)
    with pytest.raises(RuntimeFailureError, match="timed out"):
        runtime.execute(SandboxRequest(code="", code_hash=""), tmp_path)
    assert not owners
    assert runtime.name + "-output" in removed
    assert (runtime.name in removed) == (phase == "container")


def test_uncertain_create_never_removes_foreign_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Attempt bookkeeping never substitutes for an exact ownership-label check."""
    runtime = _runtime()
    runtime.container_attempted = True
    runtime.container_created = True
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: False)
    monkeypatch.setattr(runtime, "call", lambda *arguments: calls.append(arguments))
    runtime.cleanup()
    assert not calls


def test_container_cleanup_failure_retains_mounted_volumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unconfirmed container removal must not race daemon mounts by deleting their volumes."""
    runtime = _runtime()
    runtime.container_attempted = True
    runtime.container_created = True
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    removed: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        if arguments[0] == "rm":
            msg = "Container runtime command timed out"
            raise RuntimeFailureError(msg)
        removed.append(arguments[-1])
        return CommandResult(code=0)

    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    runtime.cleanup()
    assert not removed


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        """Read deterministic elapsed time without changing the process-global clock."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Advance only the simulated wait loop."""
        self.now += seconds


@pytest.mark.parametrize("phase", ["cp", "inspect"])
def test_wait_command_deadline_is_bounded_and_cleanup_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """A slow control command consumes only the remaining execution deadline."""
    runtime = _runtime()
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    clock = _Clock()
    budgets: list[float] = []
    removed: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        if arguments[0] in {"cp", "inspect"}:
            budgets.append(timeout)
            if arguments[0] == phase:
                clock.now += timeout
                msg = "Container runtime command timed out"
                raise RuntimeFailureError(msg)
            clock.now += 0.1
            return CommandResult(code=1)
        if arguments[0] == "rm" or arguments[:2] == ("volume", "rm"):
            removed.append(arguments[-1])
        return CommandResult(code=0)

    monkeypatch.setattr("datakeel.operators.custom_container.time", clock)
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "verify_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "arguments", lambda _request, _directory: ["create"])
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    request = SandboxRequest(code="", code_hash="", limits=SandboxLimits(timeout_seconds=0.4))
    result = runtime.execute(request, tmp_path)
    assert result.exit_reason == "timeout"
    assert clock.now == pytest.approx(0.4)
    assert budgets == pytest.approx([0.4] if phase == "cp" else [0.4, 0.3])
    assert removed == [runtime.name, *runtime.attempted_volumes]


@pytest.mark.parametrize("phase", ["usage", "pause"])
def test_shared_deadline_cannot_be_extended_by_forged_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """Untrusted completion cannot grant more execution time during measurement or freezing."""
    runtime = _runtime()
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    clock = _Clock()
    budgets: list[tuple[str, float]] = []
    removed: list[str] = []
    usage = ContainerUsage(events="oom_kill 0\n", peak="100\n", cpu="usage_usec 10\n")

    def forged_status(_deadline: float) -> WorkerStatus:
        clock.now = 0.35
        return WorkerStatus(exit_code=0)

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        operation = arguments[0]
        if operation in {"start", "exec", "pause"}:
            budgets.append((operation, timeout))
            if operation == phase or (operation == "exec" and phase == "usage"):
                clock.now += timeout
                msg = "Container runtime command timed out"
                raise RuntimeFailureError(msg)
            if operation == "exec":
                clock.now += 0.02
                return CommandResult(code=0, stdout=usage.model_dump_json().encode())
        if operation == "rm" or arguments[:2] == ("volume", "rm"):
            removed.append(arguments[-1])
        return CommandResult(code=0)

    monkeypatch.setattr("datakeel.operators.custom_container.time", clock)
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "verify_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "arguments", lambda _request, _directory: ["create"])
    monkeypatch.setattr(runtime, "wait", forged_status)
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    request = SandboxRequest(code="", code_hash="", limits=SandboxLimits(timeout_seconds=0.4))
    result = runtime.execute(request, tmp_path)
    assert result.exit_reason == "timeout"
    assert clock.now == pytest.approx(0.4)
    assert budgets[0] == ("start", 30)
    assert budgets[1][1] == pytest.approx(0.05)
    if phase == "pause":
        assert budgets[2][1] == pytest.approx(0.03)
    assert (result.resources.cpu_seconds, result.resources.memory_peak_bytes) == (
        (0.00001, 100) if phase == "pause" else (None, None)
    )
    assert removed == [runtime.name, *runtime.attempted_volumes]


def test_late_create_settles_before_removing_original_volumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timed-out create may appear later; retain mounts until its owned container is removed."""
    runtime = _runtime()
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    clock = _Clock()
    inspected = 0
    operations: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        nonlocal inspected
        operation = arguments[0]
        operations.append(operation)
        if operation == "create":
            assert timeout == 30
            msg = "Container runtime command timed out"
            raise RuntimeFailureError(msg)
        if operation == "inspect":
            inspected += 1
            return (
                CommandResult(code=1)
                if inspected == 1
                else CommandResult(code=0, stdout=runtime.name.encode())
            )
        return CommandResult(code=0)

    monkeypatch.setattr("datakeel.operators.custom_container.time", clock)
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    with pytest.raises(RuntimeFailureError, match="timed out"):
        runtime.execute(SandboxRequest(code="", code_hash=""), tmp_path)
    assert operations == ["create", "inspect", "inspect", "rm", "volume", "volume"]
    assert not runtime.container_created


@pytest.mark.parametrize("visible_owner", [None, "foreign"])
def test_unsettled_or_foreign_create_retains_volumes_without_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, visible_owner: str | None
) -> None:
    """Never remove foreign containers or volumes still needed by an unresolved daemon create."""
    runtime = _runtime()
    runtime.attempted_volumes = [runtime.name + "-output", runtime.name + "-status"]
    clock = _Clock()
    operations: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        operations.append(arguments[0])
        if arguments[0] == "create":
            msg = "Container runtime command timed out"
            raise RuntimeFailureError(msg)
        clock.now += timeout
        return (
            CommandResult(code=1)
            if visible_owner is None
            else CommandResult(code=0, stdout=visible_owner.encode())
        )

    monkeypatch.setattr("datakeel.operators.custom_container.time", clock)
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "call", call)
    with pytest.raises(RuntimeFailureError, match="timed out"):
        runtime.execute(SandboxRequest(code="", code_hash=""), tmp_path)
    assert set(operations) == {"create", "inspect"}
    assert clock.now <= 30


@pytest.mark.parametrize("field", ["owner", "driver", "type", "device", "options"])
def test_replaced_or_unbounded_volume_is_rejected_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """Even a successful create cannot start if its actual mounts lost any isolation field."""
    runtime = _runtime()
    request = SandboxRequest(code="", code_hash="")
    operations: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        operations.append(arguments[0])
        if arguments[:2] == ("volume", "inspect"):
            name, options = next(iter(runtime.volume_options(request).items()))
            values = [name, "local", runtime.name, "tmpfs", "tmpfs", options]
            values[{"owner": 2, "driver": 1, "type": 3, "device": 4, "options": 5}[field]] = (
                "invalid"
            )
            return CommandResult(code=0, stdout="\n".join(values).encode())
        return CommandResult(code=0)

    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "cleanup", lambda: None)
    monkeypatch.setattr(runtime, "call", call)
    with pytest.raises(RuntimeFailureError, match="tmpfs volume configuration"):
        runtime.execute(request, tmp_path)
    assert operations == ["create", "volume"]


def test_execution_deadline_starts_after_confirmed_start_without_prepare_credit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slow create/start control calls neither consume nor extend the user execution budget."""
    runtime = _runtime()
    clock = _Clock()
    budgets: list[tuple[str, float]] = []
    supervisor_timeout: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        budgets.append((arguments[0], timeout))
        if arguments[0] == "create":
            supervisor_timeout.append(arguments[-1])
            clock.now += 29
        elif arguments[0] == "start":
            clock.now += 2
        elif arguments[0] in {"cp", "inspect"}:
            clock.now += timeout
            msg = "Container runtime command timed out"
            raise RuntimeFailureError(msg)
        return CommandResult(code=0)

    monkeypatch.setattr("datakeel.operators.custom_container.time", clock)
    monkeypatch.setattr(runtime, "create_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "verify_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    request = SandboxRequest(code="", code_hash="", limits=SandboxLimits(timeout_seconds=0.4))
    result = runtime.execute(request, tmp_path)
    assert result.exit_reason == "timeout"
    assert supervisor_timeout == ["0.4"]
    assert budgets[:3] == [("create", 30), ("start", 30), ("cp", pytest.approx(0.4))]
    assert clock.now == pytest.approx(31.4)
    assert budgets[-1] == ("rm", 10)


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_failed_start_raises_and_removes_owned_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A rejected or unresponsive start never reports success and still cleans up."""
    runtime = _runtime()
    removed: list[str] = []

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        if arguments[0] == "start":
            if failure == "timeout":
                msg = "Container runtime command timed out"
                raise RuntimeFailureError(msg)
            return CommandResult(code=1)
        if arguments[0] == "rm" or arguments[:2] == ("volume", "rm"):
            removed.append(arguments[-1])
        return CommandResult(code=0)

    def create_volumes(request: SandboxRequest) -> None:
        runtime.attempted_volumes = list(runtime.volume_options(request))

    monkeypatch.setattr(runtime, "create_volumes", create_volumes)
    monkeypatch.setattr(runtime, "verify_volumes", lambda _request: None)
    monkeypatch.setattr(runtime, "owned", lambda _resource, _name: True)
    monkeypatch.setattr(runtime, "call", call)
    with pytest.raises(RuntimeFailureError):
        runtime.execute(SandboxRequest(code="", code_hash=""), tmp_path)
    assert removed == [runtime.name, runtime.name + "-output", runtime.name + "-status"]


def test_supervisor_timeout_status_is_reported_as_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-container deadline report maps to the host timeout reason without outputs."""
    runtime = _runtime()
    logs = io.BytesIO()
    with tarfile.open(fileobj=logs, mode="w") as archive:
        entry = tarfile.TarInfo("status/stderr")
        entry.size = 7
        archive.addfile(entry, io.BytesIO(b"stopped"))
    monkeypatch.setattr(
        runtime,
        "call",
        lambda *_arguments, **_kwargs: CommandResult(code=0, stdout=logs.getvalue()),
    )
    result = runtime.collect(
        SandboxRequest(code="", code_hash=""), WorkerStatus(exit_code=-9, reason="timeout")
    )
    assert (result.success, result.exit_reason, result.outputs) == (False, "timeout", ())
    assert result.stderr == "stopped"


@pytest.mark.parametrize("source", ["/status/status.json", "/status/.", "/output/."])
def test_inflated_copy_is_output_rejection_not_runtime_failure(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    """User-controlled archive size is attributed to invalid output in every copy path."""
    runtime = _runtime()

    def call(*arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        msg = "Container runtime output exceeds the byte limit"
        raise RuntimeOutputLimitError(msg)

    monkeypatch.setattr(runtime, "call", call)
    with pytest.raises(OutputRejectedError, match="byte limit"):
        runtime.copy_out(source, 1024, None if source.endswith(".") else time.monotonic() + 10)
