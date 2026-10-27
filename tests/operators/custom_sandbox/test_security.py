# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise real container isolation against generated hostile operator fixtures."""

import hashlib
import textwrap
import time
from pathlib import Path

import pytest

from datakeel.core.custom_sandbox import SandboxInput, SandboxLimits, SandboxRequest, SandboxResult
from datakeel.core.settings import Settings
from datakeel.operators.custom_container import ContainerSandbox
from datakeel.operators.custom_process import CommandResult
from datakeel.operators.custom_sandbox import run_sandbox

_SCHEMA = {"type": "object", "additionalProperties": False}
type _RuntimeEvent = tuple[str, str, float]


def _observe_execution(monkeypatch: pytest.MonkeyPatch) -> list[_RuntimeEvent]:
    events: list[_RuntimeEvent] = []
    original = ContainerSandbox.call

    def call(
        sandbox: ContainerSandbox, *arguments: str, maximum: int = 65536, timeout: float = 10
    ) -> CommandResult:
        if arguments[0] == "start":
            events.append(("start", sandbox.name, time.monotonic()))
        result = original(sandbox, *arguments, maximum=maximum, timeout=timeout)
        if not result.code:
            if arguments[:2] == ("rm", "--force") and arguments[-1] == sandbox.name:
                events.append(("removed", sandbox.name, time.monotonic()))
            elif arguments[:2] == ("volume", "rm"):
                events.append(("volume_removed", arguments[-1], time.monotonic()))
        return result

    monkeypatch.setattr(ContainerSandbox, "call", call)
    return events


def _assert_execution_window(events: list[_RuntimeEvent], result: SandboxResult) -> str:
    name, started = next((name, stamp) for event, name, stamp in events if event == "start")
    removed = next(stamp for event, owner, stamp in events if event == "removed" and owner == name)
    execution_window = removed - started
    assert 0 <= execution_window < 5
    assert result.resources.wall_seconds >= execution_window
    return name


def execute(code: str, settings: Settings, **limits: float) -> SandboxResult:
    """Run an untrusted source fixture through the exact production facade."""
    source = textwrap.dedent(code)
    request = SandboxRequest(
        code=source,
        code_hash=hashlib.sha256(source.encode()).hexdigest(),
        parameter_schema=_SCHEMA,
        metadata_schema=_SCHEMA,
        inputs=(SandboxInput(name="selected.txt", content=b"selected input"),),
        limits=SandboxLimits(**limits),
    )
    return run_sandbox(request, settings)


def test_container_selected_inputs_and_immutable_image_succeed(sandbox_settings: Settings) -> None:
    """Verify container selected inputs and immutable image succeed."""
    result = execute(
        """
        from pathlib import Path
        def run(inputs, params, ctx):
            assert Path(inputs[0]["path"]).read_bytes() == b"selected input"
            (Path(ctx["output_dir"]) / "result.txt").write_text("safe result")
            return [{"path": "result.txt", "metadata": {}}]
    """,
        sandbox_settings,
    )
    assert result.success, result.stderr
    assert result.outputs[0].content == b"safe result"
    assert result.image_digest.startswith("sha256:")
    assert result.resources.wall_seconds > 0


@pytest.mark.parametrize(
    "operation",
    [
        'socket.create_connection(("192.0.2.1", 80), timeout=0.2)',
        'socket.getaddrinfo("egress.invalid", 80)',
    ],
)
def test_container_network_and_dns_are_blocked(sandbox_settings: Settings, operation: str) -> None:
    """Verify container network and dns are blocked."""
    result = execute(
        f"""
        import socket
        from pathlib import Path
        def run(inputs, params, ctx):
            assert sorted(path.name for path in Path("/sys/class/net").iterdir()) == ["lo"]
            routes = Path("/proc/net/route").read_text().splitlines()
            assert not any(line.split()[1] == "00000000" for line in routes[1:])
            try:
                {operation}
            except OSError:
                return []
            raise RuntimeError("network escape")
    """,
        sandbox_settings,
    )
    assert result.success, result.stderr


def test_container_host_files_are_inaccessible(sandbox_settings: Settings, tmp_path: Path) -> None:
    """Verify container host files are inaccessible."""
    sentinel = tmp_path / "host-only.txt"
    sentinel.write_text("host-private-sentinel")
    result = execute(
        f"""
        from pathlib import Path
        def run(inputs, params, ctx):
            assert not Path({str(sentinel)!r}).exists()
            try:
                list(Path("/root").iterdir())
            except PermissionError:
                pass
            else:
                raise RuntimeError("root home readable")
            assert not Path("/var/run/docker.sock").exists()
            assert "host-private-sentinel" not in Path("/etc/passwd").read_text()
            try:
                import datakeel
            except ImportError:
                return []
            raise RuntimeError("platform module exposed")
    """,
        sandbox_settings,
    )
    assert result.success, result.stderr
    assert sentinel.read_text() == "host-private-sentinel"


@pytest.mark.parametrize("target", ['inputs[0]["path"]', '"/etc/injected"', '"/outside-output"'])
def test_container_input_and_root_writes_are_blocked(
    sandbox_settings: Settings, target: str
) -> None:
    """Verify container input and root writes are blocked."""
    result = execute(
        f"""
        from pathlib import Path
        def run(inputs, params, ctx):
            try:
                Path({target}).write_text("tampered")
            except OSError:
                return []
            raise RuntimeError("write escaped output tmpfs")
    """,
        sandbox_settings,
    )
    assert result.success, result.stderr


def test_container_environment_does_not_inherit_secrets(
    sandbox_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify container environment does not inherit secrets."""
    monkeypatch.setenv("DATAKEEL_TEST_SECRET", "generated-secret-sentinel")
    result = execute(
        """
        import os
        def run(inputs, params, ctx):
            assert "DATAKEEL_TEST_SECRET" not in os.environ
            assert "OPENAI_API_KEY" not in os.environ
            assert "ANTHROPIC_API_KEY" not in os.environ
            assert "generated-secret-sentinel" not in str(os.environ)
            assert os.getuid() != 0
            return []
    """,
        sandbox_settings,
    )
    assert result.success, result.stderr


def test_container_fork_bomb_is_limited(sandbox_settings: Settings) -> None:
    """Verify container fork bomb is limited."""
    result = execute(
        """
        import os
        import time
        def run(inputs, params, ctx):
            for _ in range(80):
                try:
                    pid = os.fork()
                except OSError:
                    return []
                if pid == 0:
                    time.sleep(60)
                    os._exit(0)
            raise RuntimeError("process limit did not apply")
    """,
        sandbox_settings,
        pids=16,
    )
    assert result.success, result.stderr


def test_container_memory_bomb_is_limited(sandbox_settings: Settings) -> None:
    """Verify container memory bomb is limited."""
    result = execute(
        """
        def run(inputs, params, ctx):
            values = bytearray(512 * 1024 * 1024)
            return [] if values else []
    """,
        sandbox_settings,
        memory_mb=64,
    )
    assert not result.success
    assert result.exit_reason == "memory_limit", result.stderr
    assert not result.outputs


def test_container_infinite_loop_is_terminated(
    sandbox_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify container infinite loop is terminated."""
    events = _observe_execution(monkeypatch)
    result = execute(
        """
        def run(inputs, params, ctx):
            while True:
                pass
    """,
        sandbox_settings,
        timeout_seconds=0.4,
    )
    assert result.exit_reason == "timeout", result.stderr
    _assert_execution_window(events, result)
    assert not result.outputs


def test_container_output_bomb_is_bounded(sandbox_settings: Settings) -> None:
    """Verify container output bomb is bounded."""
    result = execute(
        """
        from pathlib import Path
        def run(inputs, params, ctx):
            with (Path(ctx["output_dir"]) / "large").open("wb") as stream:
                for _ in range(1000):
                    stream.write(b"x" * 65536)
            return [{"path": "large", "metadata": {}}]
    """,
        sandbox_settings,
        max_output_bytes=4096,
        max_file_bytes=2048,
        max_output_files=1,
    )
    assert not result.success
    assert result.exit_reason in {"code_error", "invalid_output"}
    assert not result.outputs


@pytest.mark.parametrize("link", ["symlink", "hardlink", "fifo"])
def test_container_output_links_and_special_files_are_rejected(
    sandbox_settings: Settings, link: str
) -> None:
    """Verify container output links and special files are rejected."""
    operation = {
        "symlink": 'os.symlink("/etc/passwd", output / "bad")',
        "hardlink": (
            '(output / "original").write_text("data"); os.link(output / "original", output / "bad")'
        ),
        "fifo": 'os.mkfifo(output / "bad")',
    }[link]
    result = execute(
        f"""
        import os
        from pathlib import Path
        def run(inputs, params, ctx):
            output = Path(ctx["output_dir"])
            {operation}
            return [{{"path": "bad", "metadata": {{}}}}]
    """,
        sandbox_settings,
    )
    assert result.exit_reason == "invalid_output", result.stderr
    assert not result.outputs


def test_container_log_bomb_is_bounded(sandbox_settings: Settings) -> None:
    """Verify container log bomb is bounded."""
    result = execute(
        """
        import os
        def run(inputs, params, ctx):
            while True:
                os.write(1, b"x" * 65536)
    """,
        sandbox_settings,
        max_log_bytes=1024,
    )
    assert not result.success
    assert result.exit_reason == "log_limit", result.stderr
    assert len(result.stdout.encode()) <= 1024
    assert not result.outputs


def test_container_capabilities_privilege_and_cpu_controls_apply(
    sandbox_settings: Settings,
) -> None:
    """Check actual kernel isolation settings rather than only the runtime arguments."""
    result = execute(
        """
        import os
        from pathlib import Path
        def run(inputs, params, ctx):
            status = Path("/proc/self/status").read_text()
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            assert int(fields["CapEff"].strip(), 16) == 0
            assert int(fields["CapBnd"].strip(), 16) == 0
            assert fields["NoNewPrivs"].strip() == "1"
            quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
            assert quota != "max" and int(quota) / int(period) <= 0.5
            try:
                os.setuid(0)
            except PermissionError:
                return []
            raise RuntimeError("root privilege obtained")
    """,
        sandbox_settings,
        cpus=0.5,
    )
    assert result.success, result.stderr
    assert result.resources.memory_peak_bytes is not None
    assert result.resources.cpu_seconds is not None


@pytest.mark.parametrize("attack", ["count", "file_size", "metadata", "traversal", "extra_file"])
def test_container_output_contract_violations_publish_nothing(
    sandbox_settings: Settings, attack: str
) -> None:
    """Validate output limits and schema atomically on actual isolated files."""
    body = {
        "count": """
            for index in range(3):
                (output / str(index)).write_text("x")
            return [{"path": str(index), "metadata": {}} for index in range(3)]
        """,
        "file_size": """
            (output / "result").write_bytes(b"x" * 33)
            return [{"path": "result", "metadata": {}}]
        """,
        "metadata": """
            (output / "result").write_text("x")
            return [{"path": "result", "metadata": {"undeclared": "x"}}]
        """,
        "traversal": """
            (output / "result").write_text("x")
            return [{"path": "../result", "metadata": {}}]
        """,
        "extra_file": """
            (output / "undeclared").write_text("x")
            return []
        """,
    }[attack]
    source = (
        "from pathlib import Path\ndef run(inputs, params, ctx):\n"
        "    output = Path(ctx['output_dir'])\n"
    )
    source += textwrap.indent(textwrap.dedent(body).strip(), "    ")
    result = execute(source, sandbox_settings, max_output_files=2, max_file_bytes=32)
    assert result.exit_reason == "invalid_output", result.stderr
    assert not result.outputs


@pytest.mark.parametrize("attack", ["directory", "invalid_json", "symlink", "fifo"])
def test_container_hostile_status_is_rejected(sandbox_settings: Settings, attack: str) -> None:
    """Reject malicious control files without an uncaught parser or key error."""
    operation = {
        "directory": 'os.mkdir("/status/status.json")',
        "invalid_json": 'Path("/status/status.json").write_text("malformed")',
        "symlink": 'os.symlink("/etc/passwd", "/status/status.json")',
        "fifo": 'os.mkfifo("/status/status.json")',
    }[attack]
    result = execute(
        f"""
        import os
        import time
        from pathlib import Path
        def run(inputs, params, ctx):
            {operation}
            time.sleep(30)
            return []
    """,
        sandbox_settings,
        timeout_seconds=1,
    )
    assert result.exit_reason == "invalid_output", result.stderr
    assert not result.outputs


def test_container_forged_completion_cannot_extend_execution(
    sandbox_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forged completion is frozen or timed out, with every owned resource removed."""
    events = _observe_execution(monkeypatch)
    result = execute(
        """
        import json
        from pathlib import Path
        def run(inputs, params, ctx):
            pending = Path("/status/pending.json")
            pending.write_text(json.dumps({"exit_code": 0, "outputs": [], "reason": "completed"}))
            pending.rename("/status/status.json")
            while True:
                pass
        """,
        sandbox_settings,
        timeout_seconds=0.4,
    )
    assert result.exit_reason in {"completed", "timeout"}, result.stderr
    assert not result.outputs
    name = _assert_execution_window(events, result)
    assert {owner for event, owner, _stamp in events if event == "volume_removed"} == {
        name + "-output",
        name + "-status",
    }
