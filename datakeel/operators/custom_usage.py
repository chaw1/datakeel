# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Kernel resource accounting read from a sandbox cgroup by fixed host-supplied code."""

from datakeel.core.custom_sandbox import SandboxResources
from datakeel.core.models import BoundaryModel

# The reader first marks itself non-dumpable so a still-running worker cannot ptrace it.
USAGE_SOURCE = (
    "import ctypes; assert ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) == 0; "
    "from pathlib import Path; import json; p=Path('/sys/fs/cgroup'); "
    "print(json.dumps({'events':(p/'memory.events').read_text(),"
    "'peak':(p/'memory.peak').read_text(),'cpu':(p/'cpu.stat').read_text()}))"
)


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
