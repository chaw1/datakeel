# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze and execute a network-disabled, SQLite-only controlled fake-worker campaign."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path
from statistics import median
from tempfile import mkdtemp
from unittest.mock import patch

from rich.console import Console

from datakeel.core.vector_models import vector_hash
from datakeel.persistence import migrate
from datakeel.storage.database import Database
from scripts.we_e5.campaign_models import Campaign, Phase, Summary
from scripts.we_e5.fixtures import contents, explicit_case, references
from scripts.we_e5.models import NumericInput, Point, Workload
from scripts.we_e5.report import NumericReport, compare, worker_comparison
from scripts.we_e5.store import create_fixture, new_version
from scripts.we_e5.worker import run_phase


def validate_phases(phases: tuple[Phase, ...], workload: Workload) -> None:
    """Reject evidence that fails the cold/hot/one-peer invalidation contract."""
    cold, hot, incremental = phases
    count = workload.assets + workload.reference_groups
    comparisons = workload.assets * (workload.assets - 1) // 2
    valid = (
        cold.cache_before.embeddings == ()
        and cold.cache_before.globals == ()
        and cold.dispatch_count == count
        and len(cold.attempted_asset_ids) == count
        and hot.dispatch_count == 0
        and hot.attempted_asset_ids == ()
        and cold.source_version_id == hot.source_version_id
        and cold.prepared == hot.prepared
        and cold.facts_hash == hot.facts_hash
        and all(
            n.vector is not None and n.vector.cache_hits == n.vector.counts.input
            for n in hot.report.operators
        )
        and incremental.source_version_id != hot.source_version_id
        and incremental.dispatch_count == 1
        and incremental.attempted_asset_ids == ("target-00000",)
    )
    # Scope rebinding changes versioned anchors for every T; compare stable peer cache keys instead.
    before = {s.asset_id: s.cache_key for s in hot.prepared.nodes[0].inputs}
    after = {s.asset_id: s.cache_key for s in incremental.prepared.nodes[0].inputs}
    valid = valid and {key for key in before if before[key] != after[key]} == {"target-00000"}
    hot_scope = next(s.scope for s in hot.prepared.selections if s.scope is not None)
    new_scope = next(s.scope for s in incremental.prepared.selections if s.scope is not None)
    valid = valid and hot_scope.references == new_scope.references
    for node in incremental.report.operators:
        valid = (
            valid
            and node.vector is not None
            and node.vector.cache_hits
            == (count - 1 if node.operator == "evidence.vector_embed" else 0)
        )
    for phase, expected in ((cold, comparisons), (hot, 0), (incremental, comparisons)):
        valid = valid and (
            phase.pair_comparisons
            == phase.cluster_comparisons
            == phase.outlier_comparisons
            == expected
            and phase.reference_comparisons
            == (0 if phase.name == "hot" else workload.assets * workload.reference_groups)
            and sum(n.vector.fake_cost_nanos for n in phase.report.operators if n.vector) == 0
        )
    if not valid:
        msg = "cold_hot_incremental_evidence_contract_failed"
        raise ValueError(msg)


def numeric_input(phase: Phase, workload: Workload) -> NumericInput:
    """Score the actual worker's recorded vectors using predeclared synthetic text groups."""
    targets = contents(workload)
    refs = references(workload)
    reference_groups = {r.group for r in refs}
    return NumericInput(
        points=tuple(Point(asset_id=s.subject.asset_id, values=s.vector) for s in phase.samples),
        targets=tuple(t.asset_id for t in targets),
        references=tuple(r.asset_id for r in refs),
        prefix=workload.prefix,
        threshold=workload.duplicate_threshold,
        eps=workload.eps,
        min_samples=workload.min_samples,
        gap_threshold=workload.gap_threshold,
        duplicate_gold=tuple(t.group for t in targets),
        cluster_gold=tuple(t.cluster for t in targets),
        gap_gold=tuple(t.asset_id for t in targets if t.group not in reference_groups),
    )


def _summary(phases: tuple[Phase, ...], name: str) -> Summary:
    selected = [phase for phase in phases if phase.name == name]
    wall = tuple(p.wall_seconds for p in selected)
    rss = tuple(p.rss_bytes for p in selected)
    return Summary(
        phase=name,
        wall_seconds=wall,
        rss_bytes=rss,
        wall_min=min(wall),
        wall_median=median(wall),
        wall_max=max(wall),
        rss_max=max(rss),
    )


def _repetition(directory: Path, workload: Workload, index: int) -> tuple[Phase, ...]:
    directory.mkdir()
    with patch.dict(
        os.environ, {"DATAKEEL_HOME": str(directory / "home"), "DATAKEEL_ACCEL": "off"}, clear=True
    ):
        db = Database(f"sqlite:///{directory / 'campaign.sqlite'}")
        try:
            migrate(db)
            fixture = create_fixture(db, directory, workload)
            cold = run_phase(db, fixture, workload, "cold", index)
            hot = run_phase(db, fixture, workload, "hot", index)
            changed = new_version(db, fixture, directory / "changed.txt")
            incremental = run_phase(db, changed, workload, "incremental", index)
            return cold, hot, incremental
        finally:
            db.engine.dispose()


def run_campaign(destination: Path, workload: Workload, command: tuple[str, ...]) -> Campaign:
    """Write the frozen manifest first, retain every raw repeat and prohibit all sockets."""
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "workload": workload.model_dump(mode="json"),
        "targets": [t.model_dump(mode="json") for t in contents(workload)],
        "references": [r.model_dump(mode="json") for r in references(workload)],
        "numeric_oracle": explicit_case().model_dump(mode="json"),
    }
    manifest_hash = vector_hash(manifest)
    (destination / "workload.json").write_text(json.dumps(manifest, indent=2) + "\n")
    collected: list[Phase] = []
    with ExitStack() as stack:
        for target in ("getaddrinfo", "create_connection", "socket.connect", "socket.connect_ex"):
            stack.enter_context(
                patch("socket." + target, side_effect=OSError("offline_campaign_network_denied"))
            )
        for index in range(workload.repetitions):
            repeat = _repetition(destination / f"repeat-{index:02d}", workload, index)
            (destination / f"raw-{index:02d}.json").write_text(
                json.dumps([p.model_dump(mode="json") for p in repeat], indent=2) + "\n"
            )
            validate_phases(repeat, workload)
            collected.extend(repeat)
        phases = tuple(collected)
        comparisons = (
            compare(explicit_case()),
            worker_comparison(compare(numeric_input(phases[0], workload)), phases[0].recorded),
        )
    report = Campaign(
        workload=workload,
        workload_sha256=manifest_hash,
        command=command,
        phases=phases,
        environment={
            "python": platform.python_version(),
            "os": platform.platform(),
            "cpu": platform.processor(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count() or 1,
            "database": "SQLite",
            "database_version": sqlite3.sqlite_version,
            "dialect": "sqlite",
            "faiss": version("faiss-cpu"),
            "numpy": version("numpy"),
            "packaging": version("packaging"),
            "rss_platform": sys.platform,
        },
        summaries=tuple(_summary(phases, name) for name in workload.phases),
        comparisons=comparisons,
        reproducible_facts_hash=vector_hash(
            {
                "phases": [(p.name, p.facts_hash) for p in phases],
                "numeric": [_numeric_facts(c) for c in comparisons],
            }
        ),
    )
    (destination / "campaign.json").write_text(report.model_dump_json(indent=2) + "\n")
    return report


def _numeric_facts(report: NumericReport) -> dict[str, object]:
    return report.model_dump(
        exclude={"f64_wall_seconds", "faiss_wall_seconds", "normalization_wall_seconds"}
    )


def main() -> None:
    """Create a new retained run directory; repeat the exact command to verify facts hashes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/we/campaigns"))
    parser.add_argument("--assets", type=int, default=24)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    workload = Workload(assets=args.assets, repetitions=args.repetitions)
    args.output.mkdir(parents=True, exist_ok=True)
    directory = Path(mkdtemp(prefix="run-", dir=args.output))
    report = run_campaign(directory, workload, tuple(sys.argv))
    Console().print(f"Saved {directory / 'campaign.json'}; facts={report.reproducible_facts_hash}")


if __name__ == "__main__":
    main()
