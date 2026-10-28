# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure real multi-process operators and deterministic manifest quality scoring."""

from __future__ import annotations

import resource
import sys
import time
from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.core.models import FileItem
from datakeel.quality.scoring import score_quality
from datakeel.storage.database import ShardRow, TaskRow, VersionRow
from datakeel.storage.datasets import import_dataset
from datakeel.worker.queue import DatabaseQueue
from scripts.scale_bench.common import check_resources, check_space, fingerprint
from scripts.scale_bench.models import Context, ScenarioResult
from scripts.scale_bench.worker import drain, text_pipeline

if TYPE_CHECKING:
    from pathlib import Path


def _generate(context: Context) -> list[Path]:
    source = context.root / "source"
    source.mkdir()
    paths: list[Path] = []
    for index in range(context.scale.files):
        path = source / f"generated-{index:07d}.txt"
        path.write_text(
            f"Generated text record {index}; seed {context.config.seed}. "
            "Readable synthetic fixture for quality and validation.\n"
        )
        paths.append(path)
        if index % 1000 == 0:
            check_space(context.root)
    return paths


def _output(context: Context, task_id: str) -> list[FileItem]:
    with context.db.session() as session:
        task = session.get(TaskRow, task_id)
        if task is None or task.state != "COMPLETED":
            msg = "Multi-process pipeline did not complete"
            raise RuntimeError(msg)
        manifest = session.scalar(select(VersionRow.manifest).where(VersionRow.task_id == task_id))
        if manifest is None:
            msg = "Completed pipeline did not publish its real output version"
            raise RuntimeError(msg)
        files = [FileItem.model_validate(item) for item in manifest]
    if len(files) != context.scale.files or not all(
        "text_quality" in item.metadata and "empty" in item.metadata for item in files
    ):
        msg = "Real pipeline did not measure and preserve every generated input"
        raise RuntimeError(msg)
    return files


def _prepare(context: Context) -> tuple[str, float, float]:
    started = time.perf_counter()
    paths = _generate(context)
    generation_seconds = time.perf_counter() - started
    check_resources(context, reserve_bytes=context.scale.files * 8192)
    started = time.perf_counter()
    with context.db.session() as session:
        dataset = import_dataset(session, "Generated text pipeline", paths)
        session.commit()
        dataset_id = dataset.id
    import_seconds = time.perf_counter() - started
    check_resources(context)
    return dataset_id, generation_seconds, import_seconds


def run(context: Context) -> ScenarioResult:
    """Import unique tiny text files, process shards, and score the published output."""
    context = context.model_copy(
        update={
            "scale": context.scale.model_copy(update={"files": min(context.scale.files, 200_000)})
        }
    )
    check_resources(context, reserve_bytes=context.scale.files * 12 * 1024)
    dataset_id, generation_seconds, import_seconds = _prepare(context)
    workers = min(context.config.workers, context.scale.files)
    task_id = DatabaseQueue(context.db).submit(
        dataset_id, f"pipeline:{context.config.seed}", text_pipeline(), shards=workers
    )
    drained = drain(context, scoring=True)
    allocated = check_resources(context)
    outputs = _output(context, task_id)
    if drained.scored_files != len(outputs):
        msg = "Workers did not score every published output file"
        raise RuntimeError(msg)
    started = time.perf_counter()
    quality = score_quality(outputs)
    quality_seconds = time.perf_counter() - started
    with context.db.session() as session:
        attempts = list(session.scalars(select(ShardRow.attempts)))
    divisor = 1024**2 if sys.platform == "darwin" else 1024
    parent_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor
    return ScenarioResult(
        scenario="B2",
        counts={"files": len(outputs), "shards": workers, "workers": context.config.workers},
        metrics={
            "generation_seconds": generation_seconds,
            "import_seconds": import_seconds,
            "pipeline_seconds": drained.seconds,
            "quality_seconds": quality_seconds,
            "files_per_second": len(outputs) / drained.seconds,
            "quality_total": quality.total,
            "worker_scored_files": drained.scored_files,
            "worker_quality_seconds": drained.quality_seconds,
            "parent_peak_rss_mib": parent_peak,
            "summed_worker_peak_rss_mib": drained.worker_peak_rss_mib,
            "peak_rss_upper_bound_mib": parent_peak + drained.worker_peak_rss_mib,
            "retry_attempts": sum(attempts) - workers,
            "fixture_allocated_bytes": allocated,
        },
        fixture_sha256=fingerprint(
            {
                "seed": context.config.seed,
                "files": context.scale.files,
                "format": "generated-text-record-v1",
            }
        ),
        notes=(
            "L uses 200,000 physical files to keep source/object copies under the disk budget.",
            "Actual files and immutable local object publication, not metadata-only task stubs.",
            "Workers run empty/text operators and five-dimension quality scoring per output shard.",
            "Parent additionally scores the full output for global uniqueness/distribution.",
            "Direct queue/execute/relay drain excludes scheduler, webhook and action polling.",
            "RSS upper bound sums per-process lifetime peaks; peaks need not be simultaneous.",
        ),
    )
