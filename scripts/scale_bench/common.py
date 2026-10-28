# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded measurements and deterministic data identities for scale scenarios."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from typing import TYPE_CHECKING

from sqlalchemy import text

from scripts.scale_bench.models import Latency

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from pydantic import JsonValue

    from scripts.scale_bench.models import Context

MIN_FREE_BYTES = 10 * 1024**3
MAX_FIXTURE_BYTES = 8 * 1024**3


def check_space(root: Path) -> int:
    """Refuse a workload before allocating fixtures on a nearly full volume."""
    available = shutil.disk_usage(root).free
    if available < MIN_FREE_BYTES:
        message = "Less than 10 GiB free; workload refused before fixture generation"
        raise OSError(message)
    return available


def fingerprint(value: JsonValue) -> str:
    """Hash canonical logical fixture parameters, without physical temporary paths."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def elapsed[T](operation: Callable[[], T]) -> tuple[T, float]:
    """Return an operation's actual value and monotonic wall time in seconds."""
    started = time.perf_counter()
    value = operation()
    return value, time.perf_counter() - started


def summarize(values: Iterable[float], *, errors: int = 0) -> Latency:
    """Compute nearest-rank percentiles from millisecond observations."""
    ordered = sorted(values)
    if not ordered:
        return Latency(count=0, p50_ms=0, p95_ms=0, p99_ms=0, max_ms=0, errors=errors)
    return Latency(
        count=len(ordered),
        p50_ms=ordered[max(0, math.ceil(len(ordered) * 0.50) - 1)],
        p95_ms=ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
        p99_ms=ordered[max(0, math.ceil(len(ordered) * 0.99) - 1)],
        max_ms=ordered[-1],
        errors=errors,
    )


def measure(operation: Callable[[], object], repeats: int) -> Latency:
    """Measure successful calls without hiding failures or warming away their cost."""
    return summarize(elapsed(operation)[1] * 1000 for _ in range(repeats))


def check_resources(context: Context, *, reserve_bytes: int = 0) -> int:
    """Check only owned files/schema, with a conservative reserve before bulk allocation.

    Call at phase boundaries; per-row loops use check_space to avoid quadratic directory
    walks. Allocated blocks count tiny files and WALs. PostgreSQL totals include indexes
    and TOAST, restricted to the invocation's randomly named schema.
    """
    available = check_space(context.root)
    used = sum(path.stat().st_blocks * 512 for path in context.root.rglob("*") if path.is_file())
    if context.schema_name:
        with context.db.session() as session:
            used += int(
                session.scalar(
                    text(
                        "SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = :schema AND c.relkind IN ('r', 'm')"
                    ),
                    {"schema": context.schema_name},
                )
                or 0
            )
    if used + reserve_bytes > MAX_FIXTURE_BYTES:
        message = "Owned fixture would exceed the 8 GiB allocation limit"
        raise OSError(message)
    if available - reserve_bytes < MIN_FREE_BYTES:
        message = "Fixture reserve would leave less than 10 GiB free"
        raise OSError(message)
    return used
