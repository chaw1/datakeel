# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run approved code in an immutable, resource-limited Docker-compatible sandbox."""

import logging
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from datakeel.core.custom_sandbox import SandboxRequest, SandboxResources, SandboxResult
from datakeel.core.models import BoundaryModel
from datakeel.operators.custom_job import write_job
from datakeel.operators.custom_output import (
    OutputRejectedError,
    WorkerStatus,
    archive_files,
    parse_status,
    validated_outputs,
)
from datakeel.operators.custom_process import CommandResult, RuntimeFailureError, command

_DIGEST = re.compile(r"(?:[^ @]+@)?sha256:[0-9a-f]{64}\Z")
_LOGGER = logging.getLogger(__name__)
_OWNER_LABEL = "datakeel.sandbox.owner"


class ContainerUsage(BoundaryModel):
    """Read kernel accounting through an immutable interpreter before freezing processes."""

    events: str
    peak: str
    cpu: str

    def measured(self) -> SandboxResources:
        """Convert kernel counters into truthful cumulative CPU and peak memory measurements."""
        counters = dict(line.split() for line in self.cpu.splitlines())
        return SandboxResources(
            cpu_seconds=int(counters["usage_usec"]) / 1_000_000,
            memory_peak_bytes=int(self.peak.strip()),
        )

    def oom(self) -> bool:
        """Report an actual kernel OOM kill rather than trusting user-written diagnostics."""
        return int(dict(line.split() for line in self.events.splitlines()).get("oom_kill", "0")) > 0


class ContainerSandbox:
    """Own one disposable container and its bounded runtime command channel."""

    def __init__(self, image: str, environment: dict[str, str]) -> None:
        """Require a locally present image pinned by an immutable content digest."""
        executable = shutil.which("docker")
        if executable is None:
            msg = "Container backend requires a Docker-compatible runtime"
            raise RuntimeFailureError(msg)
        if not _DIGEST.fullmatch(image):
            msg = "Container image must be pinned by a sha256 digest"
            raise RuntimeFailureError(msg)
        self.executable = executable
        self.environment = environment
        self.image = image
        self.name = "datakeel-sandbox-" + uuid4().hex
        self.container_attempted = False
        self.container_created = False
        self.attempted_volumes: list[str] = []
        result = self.call("image", "inspect", image, "--format", "{{.Id}}")
        if result.code or not result.stdout.decode().strip().startswith("sha256:"):
            msg = "Pinned sandbox image is unavailable; build or load it first"
            raise RuntimeFailureError(msg)
        self.digest = result.stdout.decode().strip()

    def call(self, *arguments: str, maximum: int = 65536, timeout: float = 10) -> CommandResult:
        """Invoke a literal runtime command with a small bounded control channel."""
        return command(
            [self.executable, *arguments], self.environment, maximum=maximum, timeout=timeout
        )

    def execute(self, request: SandboxRequest, directory: Path) -> SandboxResult:
        """Freeze all processes before copying and validating the output snapshot."""
        write_job(request, directory, "/output", container=True)
        try:
            self.create_volumes(request)
            self.container_attempted = True
            created = self.call(*self.arguments(request, directory), timeout=30)
            if created.code:
                msg = "Container runtime rejected the secure sandbox configuration"
                raise RuntimeFailureError(msg)
            self.container_created = True
            self.verify_volumes(request)
            deadline = time.monotonic() + request.limits.timeout_seconds
            started = self._deadline_call(deadline, "start", self.name)
            if started is None:
                return self._timed_out()
            if started.code:
                msg = "Container runtime could not start the sandbox"
                raise RuntimeFailureError(msg)
            status = self.wait(deadline)
            if status is None:
                return self._timed_out()
            usage = self.usage(deadline)
            paused = self._deadline_call(deadline, "pause", self.name)
            if paused is None:
                return self._timed_out(usage)
            if paused.code:
                msg = "Container could not be frozen for output validation"
                raise RuntimeFailureError(msg)
            return self._frozen_result(request, status, usage)
        finally:
            self.cleanup()

    def _timed_out(self, usage: ContainerUsage | None = None) -> SandboxResult:
        return SandboxResult(
            success=False,
            exit_reason="timeout",
            image_digest=self.digest,
            resources=usage.measured() if usage is not None else SandboxResources(),
        )

    def _frozen_result(
        self, request: SandboxRequest, status: WorkerStatus, usage: ContainerUsage | None
    ) -> SandboxResult:
        try:
            result = self.collect(request, status)
        except OutputRejectedError as error:
            result = SandboxResult(
                success=False,
                exit_reason="invalid_output",
                image_digest=self.digest,
                stderr=str(error),
            )
        if usage is not None:
            changes: dict[str, object] = {"resources": usage.measured()}
            if usage.oom():
                changes.update(success=False, outputs=(), exit_reason="memory_limit")
            result = result.model_copy(update=changes)
        return result

    def arguments(self, request: SandboxRequest, directory: Path) -> list[str]:
        """Make every mandatory isolation control explicit with no host writable mount."""
        limits = request.limits
        tmpfs = "rw,noexec,nosuid,nodev,uid=65532,gid=65532,mode=700,size="
        return [
            "create",
            "--name",
            self.name,
            "--label",
            f"{_OWNER_LABEL}={self.name}",
            "--pull=never",
            "--network=none",
            "--ipc=none",
            "--read-only",
            "--user=65532:65532",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--log-driver=none",
            "--memory",
            f"{limits.memory_mb}m",
            "--memory-swap",
            f"{limits.memory_mb}m",
            "--cpus",
            str(limits.cpus),
            "--pids-limit",
            str(limits.pids),
            "--ulimit",
            "nofile=64:64",
            "--ulimit",
            "core=0:0",
            "--mount",
            f"type=bind,source={directory},target=/job,readonly",
            "--mount",
            f"type=volume,source={self.name}-output,target=/output,volume-nocopy",
            "--mount",
            f"type=volume,source={self.name}-status,target=/status,volume-nocopy",
            "--tmpfs",
            f"/tmp:{tmpfs}1048576",  # noqa: S108  # Private bounded container tmpfs.
            "--env",
            "LANG=C.UTF-8",
            self.image,
            str(limits.max_log_bytes),
        ]

    def create_volumes(self, request: SandboxRequest) -> None:
        """Use private tmpfs-backed volumes so runtime archive APIs see the frozen files."""
        for name, options in self.volume_options(request).items():
            if not self.call("volume", "inspect", name).code:
                msg = "Refusing to reuse a pre-existing sandbox output volume"
                raise RuntimeFailureError(msg)
            self.attempted_volumes.append(name)
            result = self.call(
                "volume",
                "create",
                "--driver",
                "local",
                "--opt",
                "type=tmpfs",
                "--opt",
                "device=tmpfs",
                "--opt",
                "o=" + options,
                "--label",
                f"{_OWNER_LABEL}={self.name}",
                "--label",
                "datakeel.sandbox.task=custom-operator",
                name,
            )
            if result.code:
                msg = "Container runtime requires bounded tmpfs-backed output volumes"
                raise RuntimeFailureError(msg)

    def volume_options(self, request: SandboxRequest) -> dict[str, str]:
        """Describe the complete private output-volume configuration."""
        limits = request.limits
        budgets = {
            "output": limits.max_output_bytes + limits.max_output_files * 4096,
            "status": limits.max_log_bytes * 2 + 131072,
        }
        restrictions = "uid=65532,gid=65532,mode=700,noexec,nosuid,nodev"
        return {
            f"{self.name}-{suffix}": f"size={budget},{restrictions}"
            for suffix, budget in budgets.items()
        }

    def verify_volumes(self, request: SandboxRequest) -> None:
        """Fail closed before start if daemon mounts lost their ownership or tmpfs limits."""
        template = (
            '{{.Name}}\n{{.Driver}}\n{{index .Labels "'
            + _OWNER_LABEL
            + '"}}\n{{index .Options "type"}}\n{{index .Options "device"}}\n{{index .Options "o"}}'
        )
        for name, options in self.volume_options(request).items():
            result = self.call("volume", "inspect", "--format", template, name)
            if result.code or result.stdout.decode().strip().splitlines() != [
                name,
                "local",
                self.name,
                "tmpfs",
                "tmpfs",
                options,
            ]:
                msg = "Sandbox tmpfs volume configuration could not be verified"
                raise RuntimeFailureError(msg)

    def owned(self, resource: str, name: str) -> bool:
        """Verify the per-run ownership label before deleting an exact resource name."""
        field = ".Labels" if resource == "volume" else ".Config.Labels"
        template = "{{index " + field + ' "' + _OWNER_LABEL + '"}}'
        arguments = ["volume", "inspect"] if resource == "volume" else ["inspect"]
        result = self.call(*arguments, "--format", template, name)
        return not result.code and result.stdout.decode().strip() == self.name

    def cleanup(self) -> None:
        """Keep volumes until their exact owned container is confirmed removed."""
        if self.container_attempted:
            removed = (
                self._remove_owned("container", self.name)
                if self.container_created
                else self._settle_create()
            )
            if not removed:
                _LOGGER.error(
                    "Retaining sandbox volumes after uncertain container cleanup: %s", self.name
                )
                return
        for name in self.attempted_volumes:
            self._remove_owned("volume", name)

    def _settle_create(self) -> bool:
        """Bound late daemon creation without deleting volumes it may still mount."""
        deadline = time.monotonic() + 30
        template = '{{index .Config.Labels "' + _OWNER_LABEL + '"}}'
        try:
            while time.monotonic() < deadline:
                result = self._deadline_call(deadline, "inspect", "--format", template, self.name)
                if result is None:
                    return False
                if not result.code:
                    if result.stdout.decode().strip() != self.name:
                        return False
                    removed = self._deadline_call(deadline, "rm", "--force", self.name)
                    return removed is not None and not removed.code
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        except RuntimeFailureError:
            _LOGGER.exception("Sandbox create settlement failed: %s", self.name)
        return False

    def _remove_owned(self, resource: str, name: str) -> bool:
        try:
            if not self.owned(resource, name):
                return False
            arguments = ("volume", "rm", name) if resource == "volume" else ("rm", "--force", name)
            if not self.call(*arguments).code:
                return True
            _LOGGER.error("Sandbox %s cleanup failed: %s", resource, name)
        except RuntimeFailureError:
            _LOGGER.exception("Sandbox runtime unavailable while cleaning %s: %s", resource, name)
        return False

    def wait(self, deadline: float) -> WorkerStatus | None:
        """Enforce a host wall-clock deadline even if every in-container process is hostile."""
        while time.monotonic() < deadline:
            result = self._deadline_call(
                deadline, "cp", f"{self.name}:/status/status.json", "-", maximum=131072
            )
            if result is None:
                return None
            if not result.code:
                files = archive_files(result.stdout, 65536)
                if set(files) != {"status.json"}:
                    msg = "Worker status must be exactly one regular completion file"
                    raise OutputRejectedError(msg)
                return parse_status(files["status.json"])
            state = self._deadline_call(
                deadline,
                "inspect",
                "--format",
                "{{.State.Running}} {{.State.OOMKilled}}",
                self.name,
            )
            if state is None:
                return None
            if state.stdout.decode().strip().startswith("false"):
                raise RuntimeFailureError(
                    "memory_limit" if b"true" in state.stdout else "Container supervisor exited"
                )
            time.sleep(min(0.025, max(0, deadline - time.monotonic())))
        return None

    def _deadline_call(
        self, deadline: float, *arguments: str, maximum: int = 65536
    ) -> CommandResult | None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            result = self.call(*arguments, maximum=maximum, timeout=min(10, remaining))
        except RuntimeFailureError:
            if time.monotonic() >= deadline:
                return None
            raise
        return result if time.monotonic() < deadline else None

    def usage(self, deadline: float) -> ContainerUsage | None:
        """Measure cgroup counters using fixed code that cannot be modified by the worker."""
        source = (
            "from pathlib import Path; import json; p=Path('/sys/fs/cgroup'); "
            "print(json.dumps({'events':(p/'memory.events').read_text(),"
            "'peak':(p/'memory.peak').read_text(),'cpu':(p/'cpu.stat').read_text()}))"
        )
        result = self._deadline_call(
            deadline, "exec", self.name, "/usr/local/bin/python", "-I", "-c", source
        )
        if result is None or result.code:
            return None
        try:
            return ContainerUsage.model_validate_json(result.stdout)
        except ValidationError:
            return None

    def collect(self, request: SandboxRequest, status: WorkerStatus) -> SandboxResult:
        """Reject links, special files, metadata errors, and limits on the frozen host copy."""
        limits = request.limits
        logs_result = self.call("cp", f"{self.name}:/status/.", "-", maximum=262144)
        logs = archive_files(logs_result.stdout, limits.max_log_bytes * 2 + 131072)
        stdout = logs.get("stdout", b"")[: limits.max_log_bytes].decode("utf-8", errors="ignore")
        stderr = logs.get("stderr", b"")[: limits.max_log_bytes].decode("utf-8", errors="ignore")
        reason = (
            status.reason
            if status.reason in {"completed", "code_error", "log_limit", "memory_limit"}
            else "invalid_output"
        )
        if status.exit_code or reason != "completed":
            return SandboxResult(
                success=False,
                exit_reason=reason,
                image_digest=self.digest,
                stdout=stdout,
                stderr=stderr,
            )
        budget = limits.max_output_bytes + limits.max_output_files * 2048 + 16384
        result = self.call("cp", f"{self.name}:/output/.", "-", maximum=budget)
        if result.code:
            msg = "Container outputs could not be copied"
            raise OutputRejectedError(msg)
        outputs = validated_outputs(
            archive_files(result.stdout, limits.max_output_bytes), status, request
        )
        return SandboxResult(
            success=True,
            exit_reason="completed",
            image_digest=self.digest,
            outputs=outputs,
            stdout=stdout,
            stderr=stderr,
        )
