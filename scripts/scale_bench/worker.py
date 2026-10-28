# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run real leased tasks in isolated processes and test a pre-publication crash."""

import json
import multiprocessing
import resource
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy import event, func, select

from datakeel.core.models import FileItem
from datakeel.pipeline import Pipeline
from datakeel.quality.scoring import score_quality
from datakeel.storage.database import Database, EventRow, OutboxRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.datasets import import_dataset
from datakeel.worker.queue import DatabaseQueue, Lease
from datakeel.worker.runner import execute
from scripts.scale_bench.common import check_resources, check_space, fingerprint
from scripts.scale_bench.models import BenchModel, Context, ScenarioResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from multiprocessing.process import BaseProcess

    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


class WorkerSpec(BenchModel):
    """Pass only the benchmark database and its private schema to child processes."""

    database_url: SecretStr
    root: Path
    schema_name: str | None
    index: int
    crash: bool = False
    scoring: bool = False


class DrainResult(BenchModel):
    """Record process outcomes separately from durable publication counts."""

    seconds: float
    executed_attempts: int
    rejected_publications: int
    killed_workers: int
    killed_exit_code: int
    worker_peak_rss_mib: float
    scored_files: int
    quality_seconds: float


def text_pipeline() -> Pipeline:
    """Use real empty-file validation and text quality operators without remote calls."""
    return Pipeline.model_validate(
        {
            "nodes": [
                {
                    "id": "empty",
                    "operator": "file.empty_check",
                    "inputs": {"files": "$input.files"},
                },
                {"id": "modality", "kind": "route", "inputs": {"files": "empty.files"}},
                {
                    "id": "quality",
                    "operator": "text.quality",
                    "inputs": {"files": "modality.text"},
                },
            ],
            "outputs": ["quality.files"],
        }
    )


def _database(spec: WorkerSpec) -> Database:
    database = Database(spec.database_url.get_secret_value())
    if spec.schema_name is not None:
        schema = spec.schema_name

        @event.listens_for(database.engine, "connect")
        def schema_path(connection: "DBAPIConnection", _record: "ConnectionPoolEntry") -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
            cursor.close()

    return database


def _crash_window(database: Database, marker: Path) -> None:
    def pause(_connection: "Connection", _cursor: object, statement: str, *_args: object) -> None:
        if statement.startswith("UPDATE task_shards SET") and "outputs=" in statement:
            marker.write_text("real operators finished; output transaction has not committed\n")
            time.sleep(30)
            msg = "Crash controller did not terminate its worker"
            raise TimeoutError(msg)

    event.listen(database.engine, "before_cursor_execute", pause)


def _worker(spec: WorkerSpec) -> None:
    database = _database(spec)
    if spec.crash:
        _crash_window(database, spec.root / "crash-ready")
    queue = DatabaseQueue(database, lease_seconds=1)
    attempts, rejected, scored, quality_seconds = 0, 0, 0, 0.0
    while lease := queue.claim():
        attempts += 1
        if spec.crash:
            (spec.root / "victim-claimed").touch()
        accepted = execute(queue, lease)
        rejected += not accepted
        if spec.scoring and accepted:
            measured, seconds = _score_outputs(database, lease)
            scored += measured
            quality_seconds += seconds
        queue.relay()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (spec.root / f"worker-{spec.index}.json").write_text(
        json.dumps(
            {
                "attempts": attempts,
                "rejected": rejected,
                "rss": peak,
                "scored": scored,
                "quality_seconds": quality_seconds,
            }
        )
    )
    database.engine.dispose()


def _score_outputs(database: Database, lease: Lease) -> tuple[int, float]:
    started = time.perf_counter()
    with database.session() as session:
        values = session.scalar(select(ShardRow.outputs).where(ShardRow.id == lease.shard_id))
    files = [FileItem.model_validate(value) for value in values or []]
    quality = score_quality(files)
    return quality.file_count, time.perf_counter() - started


def _wait_marker(process: "BaseProcess", marker: Path) -> None:
    deadline = time.monotonic() + 60
    while not marker.exists():
        if not process.is_alive() or time.monotonic() >= deadline:
            msg = "Victim worker did not reach the real pre-publication crash window"
            raise RuntimeError(msg)
        time.sleep(0.01)


def _kill_at_publication(process: "BaseProcess", marker: Path) -> int:
    _wait_marker(process, marker)
    process.kill()
    process.join(timeout=10)
    exit_code = process.exitcode
    if exit_code is None or exit_code != -signal.SIGKILL:
        msg = "Benchmark-owned worker did not terminate with SIGKILL"
        raise RuntimeError(msg)
    return exit_code


def drain(context: Context, *, crash: bool = False, scoring: bool = False) -> DrainResult:
    """Execute and recover real tasks, killing only a process created by this call."""
    count = context.config.workers
    specs = [
        WorkerSpec(
            database_url=SecretStr(context.db.engine.url.render_as_string(hide_password=False)),
            root=context.root,
            schema_name=context.schema_name,
            index=index,
            crash=crash and index == 0,
            scoring=scoring,
        )
        for index in range(count)
    ]
    factory = multiprocessing.get_context("spawn")
    processes = [factory.Process(target=_worker, args=(spec,)) for spec in specs]
    started = time.perf_counter()
    killed_exit_code = 0
    try:
        processes[0].start()
        if crash:
            _wait_marker(processes[0], context.root / "victim-claimed")
        for process in processes[1:]:
            process.start()
        if crash:
            killed_exit_code = _kill_at_publication(processes[0], context.root / "crash-ready")
            time.sleep(1.1)
            DatabaseQueue(context.db, lease_seconds=1).reap()
            replacement = factory.Process(
                target=_worker, args=(specs[0].model_copy(update={"crash": False}),)
            )
            processes.append(replacement)
            replacement.start()
        _join(processes[int(crash) :])
        queue = DatabaseQueue(context.db, lease_seconds=1)
        queue.relay()
    finally:
        for process in processes:
            if process.pid is not None and process.is_alive():
                process.terminate()
                process.join(timeout=10)
    records = [json.loads(path.read_text()) for path in context.root.glob("worker-*.json")]
    divisor = 1024**2 if sys.platform == "darwin" else 1024
    return DrainResult(
        seconds=time.perf_counter() - started,
        executed_attempts=sum(row["attempts"] for row in records) + int(crash),
        rejected_publications=sum(row["rejected"] for row in records),
        killed_workers=int(crash),
        killed_exit_code=killed_exit_code,
        worker_peak_rss_mib=sum(row["rss"] for row in records) / divisor,
        scored_files=sum(row["scored"] for row in records),
        quality_seconds=sum(row["quality_seconds"] for row in records),
    )


def _join(processes: "Sequence[BaseProcess]") -> None:
    deadline = time.monotonic() + 3600
    for process in processes:
        process.join(timeout=max(0, deadline - time.monotonic()))
        if process.exitcode != 0:
            msg = f"Benchmark worker failed or timed out: exit={process.exitcode}"
            raise RuntimeError(msg)


def _counts(database: Database) -> dict[str, int]:
    with database.session() as session:
        completed = (
            session.scalar(
                select(func.count()).select_from(TaskRow).where(TaskRow.state == "COMPLETED")
            )
            or 0
        )
        tasks = session.scalar(select(func.count()).select_from(TaskRow)) or 0
        versions = (
            session.scalar(
                select(func.count()).select_from(VersionRow).where(VersionRow.task_id.is_not(None))
            )
            or 0
        )
        output_files = (
            session.scalar(
                select(func.sum(func.json_array_length(VersionRow.manifest))).where(
                    VersionRow.task_id.is_not(None)
                )
            )
            or 0
        )
        outbox = session.scalar(select(func.count()).select_from(OutboxRow)) or 0
        terminal = (
            session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(EventRow.idempotency_key.like("task:%:terminal"))
            )
            or 0
        )
        attempts = session.scalar(select(func.sum(ShardRow.attempts))) or 0
        pipeline_events = (
            session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(EventRow.idempotency_key.like("shard:%:node:%"))
            )
            or 0
        )
    return {
        "tasks": tasks,
        "completed_tasks": completed,
        "output_versions": versions,
        "output_files": output_files,
        "pipeline_events": pipeline_events,
        "terminal_outbox_events": outbox,
        "terminal_events": terminal,
        "claim_attempts": attempts,
        "retry_attempts": attempts - tasks,
        "lost_tasks": tasks - completed,
        "duplicate_publications": max(0, versions - tasks),
    }


def run(context: Context) -> ScenarioResult:
    """Drain generated tasks after a SIGKILL between real operators and publication."""
    check_resources(context, reserve_bytes=context.scale.tasks * 32 * 1024)
    content = f"Generated worker fixture seed {context.config.seed}; plain readable words.\n"
    path = context.root / "generated-worker.txt"
    path.write_text(content)
    with context.db.session() as session:
        dataset = import_dataset(session, "Generated worker recovery", [path])
        session.commit()
        dataset_id = dataset.id
    queue = DatabaseQueue(context.db)
    definition = text_pipeline()
    submitted = time.perf_counter()
    first = ""
    for index in range(context.scale.tasks):
        task = queue.submit(dataset_id, f"worker:{context.config.seed}:{index}", definition)
        if not first:
            first = task
        if index % 500 == 0:
            check_space(context.root)
    submission_seconds = time.perf_counter() - submitted
    check_resources(context)
    if queue.submit(dataset_id, f"worker:{context.config.seed}:0", definition) != first:
        msg = "Submission idempotency did not return the existing task"
        raise RuntimeError(msg)
    drained = drain(context, crash=True)
    allocated = check_resources(context)
    counts = _counts(context.db)
    if any(counts[key] for key in ("lost_tasks", "duplicate_publications")) or (
        counts["terminal_events"] != counts["tasks"]
        or counts["terminal_outbox_events"] != counts["tasks"]
        or counts["output_files"] != counts["tasks"]
        or counts["pipeline_events"] != 2 * counts["tasks"]
        or counts["retry_attempts"] != 1
    ):
        msg = "Worker recovery did not preserve exactly one durable completion per task"
        raise RuntimeError(msg)
    return ScenarioResult(
        scenario="B6",
        counts={**counts, "workers": context.config.workers},
        metrics={
            **drained.model_dump(),
            "submission_seconds": submission_seconds,
            "tasks_per_second": context.scale.tasks / drained.seconds,
            "fixture_allocated_bytes": allocated,
            "lease_seconds": 1.0,
        },
        fixture_sha256=fingerprint({"content": content, "tasks": context.scale.tasks}),
        notes=(
            "Real queue claim, execute(), empty validation and text quality operators; no model.",
            "Direct queue/execute/relay drain excludes scheduler, webhook and action polling.",
            "SIGKILL occurs after real operators, before output transaction SQL/commit.",
            "One retry repeats computation; duplicate durable publications are counted separately.",
            "Worker RSS is the sum of surviving processes' peak RSS; killed worker is excluded.",
        ),
    )
