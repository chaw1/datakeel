# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen inputs and measurements shared by capacity workloads."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from datakeel.storage.database import Database


class BenchModel(BaseModel):
    """Reject ambiguous benchmark inputs and freeze measurement envelopes."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class Scale(BenchModel):
    """Explicit fixture sizes; M is the capacity acceptance workload."""

    files: int
    tables: int
    columns: int
    edges: int
    fact_rows_sqlite: int
    fact_rows_pg: int
    tasks: int
    graph_edges: int
    duration_seconds: float
    virtual_users: int


SCALES = {
    "S": Scale(
        files=128,
        tables=20,
        columns=400,
        edges=100,
        fact_rows_sqlite=1000,
        fact_rows_pg=1000,
        tasks=16,
        graph_edges=1000,
        duration_seconds=2,
        virtual_users=4,
    ),
    "M": Scale(
        files=100_000,
        tables=10_000,
        columns=200_000,
        edges=50_000,
        fact_rows_sqlite=1_000_000,
        fact_rows_pg=10_000_000,
        tasks=10_000,
        graph_edges=1_000_000,
        duration_seconds=300,
        virtual_users=50,
    ),
    "L": Scale(
        files=1_000_000,
        tables=20_000,
        columns=400_000,
        edges=100_000,
        fact_rows_sqlite=2_000_000,
        fact_rows_pg=20_000_000,
        tasks=20_000,
        graph_edges=2_000_000,
        duration_seconds=300,
        virtual_users=50,
    ),
}


class Config(BenchModel):
    """Select one reproducible workload and an explicitly selected local stack."""

    scenario: Literal["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]
    size: Literal["S", "M", "L"] = "S"
    stack: Literal["sqlite", "postgres"] = "sqlite"
    seed: int = 23
    repeats: int = Field(default=20, ge=1, le=1000)
    workers: int = Field(default=8, ge=1, le=32)
    think_ms: int = Field(default=1000, ge=0, le=60_000)
    duration_seconds: float | None = Field(default=None, gt=0, le=3600)


class Context(BenchModel):
    """Own the isolated database and temporary files for exactly one scenario."""

    config: Config
    scale: Scale
    db: Database
    root: Path
    schema_name: str | None = None


class Latency(BenchModel):
    """Milliseconds measured at the documented application boundary."""

    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    errors: int = 0


class ScenarioResult(BenchModel):
    """Typed, JSON-safe scenario measurements and explicit limitations."""

    scenario: str
    counts: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)
    latencies: dict[str, Latency] = Field(default_factory=dict)
    fixture_sha256: str = ""
    notes: tuple[str, ...] = ()
