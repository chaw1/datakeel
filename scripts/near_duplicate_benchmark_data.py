# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate reproducible hash workloads and typed, machine-readable measurements."""

import hashlib
import os
import platform
import random
import struct
import subprocess
import sys
from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel

Mode = Literal["prefix", "exact"]
Implementation = Literal["python", "rust"]


class Workload(BoundaryModel):
    """Bind generated hashes to independent, planted direct-pair ground truth."""

    hashes: tuple[int, ...]
    planted: tuple[tuple[int, int, int], ...]
    digest: str


class Measurement(BoundaryModel):
    """Record a completed comparison or an actual, bounded child-process timeout."""

    size: int = Field(ge=1)
    implementation: Implementation
    mode: Mode
    status: Literal["completed", "timeout"]
    elapsed_seconds: float = Field(ge=0)
    wall_seconds: float = Field(ge=0)
    peak_rss_bytes: int = Field(ge=0)
    timeout_seconds: float = Field(gt=0)
    seed: int
    threshold: Literal[8] = 8
    prefix_bits: Literal[4] = 4
    planted_pairs: int = Field(ge=0)
    found_planted_pairs: int | None = Field(default=None, ge=0)
    recall: float | None = Field(default=None, ge=0, le=1)
    returned_pairs: int | None = Field(default=None, ge=0)
    result_digest: str | None = None
    workload_digest: str | None = None
    implementation_version: str | None = None


class Machine(BoundaryModel):
    """Describe the local benchmark machine without recording its hostname or user."""

    system: str
    release: str
    architecture: str
    processor: str
    logical_cpus: int
    memory_bytes: int | None = None
    python_version: str


def generate_workload(size: int, seed: int = 20261027) -> Workload:
    """Plant one near-duplicate pair per 100 hashes, half crossing the prefix boundary."""
    if size < 1:
        message = "Workload size must be positive"
        raise ValueError(message)
    generator = random.Random(seed)  # noqa: S311  # Reproducible synthetic data, not secrets.
    hashes = [generator.getrandbits(64) for _ in range(size)]
    planted: list[tuple[int, int, int]] = []
    for index in range(size // 100):
        left, right = 2 * index, 2 * index + 1
        distance = index % 8 + 1
        positions = generator.sample(range(60), distance)
        if index % 2:
            positions[0] = 60 + index % 4
        hashes[right] = hashes[left] ^ sum(1 << bit for bit in positions)
        planted.append((left, right, distance))
    digest = hashlib.sha256()
    for value in hashes:
        digest.update(struct.pack("<Q", value))
    return Workload(hashes=tuple(hashes), planted=tuple(planted), digest=digest.hexdigest())


def machine_information() -> Machine:
    """Read CPU and RAM information from local operating-system utilities only."""
    processor = platform.processor() or platform.machine()
    memory = None
    logical_cpus = os.cpu_count() or 1
    if sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"],
            capture_output=True,
            text=True,
            check=True,
        )
        processor, memory_text, cpu_text = result.stdout.strip().splitlines()
        memory, logical_cpus = int(memory_text), int(cpu_text)
    return Machine(
        system=platform.system(),
        release=platform.release(),
        architecture=platform.machine(),
        processor=processor,
        logical_cpus=logical_cpus,
        memory_bytes=memory,
        python_version=platform.python_version(),
    )
