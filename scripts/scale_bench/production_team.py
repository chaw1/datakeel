# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""B8: virtual annotators claim, save and submit team tasks while reapers reclaim leases.

Each virtual annotator works in its own thread; threads are spread across spawned processes
so the database, not one interpreter lock, is the shared resource. Latencies are measured at
the controlled-action service boundary (prepare plus execute), the same calls the Web API and
CLI make for every claim, save and submit, without HTTP serialization.
"""

from __future__ import annotations

import json
import multiprocessing
import random
import threading
import time
from collections import Counter
from pathlib import Path  # noqa: TC003  # Pydantic resolves AnnotatorSpec.root at runtime.
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy import event

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import Database
from datakeel.storage.production_leases import LeaseExpiredError
from datakeel.storage.production_reaper import reap_expired_leases
from scripts.scale_bench.common import check_resources, fingerprint, summarize
from scripts.scale_bench.models import BenchModel, Context, ScenarioResult
from scripts.scale_bench.production_seed import (
    claim_overlaps,
    register_annotators,
    run_action,
    seed_project,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from multiprocessing.process import BaseProcess

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

LEASE_MINUTES = 1
SAVES_PER_TASK = 3
ABANDON_EVERY = 40
REAPER_PROCESSES = 2
REAPER_INTERVAL_SECONDS = 2.0
B8_SECONDS = 600.0
_OPERATIONS = ("next", "save", "submit")


class AnnotatorSpec(BenchModel):
    """Everything one child process needs, with the database URL kept secret in reprs."""

    database_url: SecretStr
    schema_name: str | None
    root: Path
    index: int
    project_id: str
    actors: tuple[str, ...]
    deadline: float
    think_ms: int
    seed: int


def _database(spec: AnnotatorSpec) -> Database:
    database = Database(spec.database_url.get_secret_value())
    if spec.schema_name is not None:
        schema = spec.schema_name

        @event.listens_for(database.engine, "connect")
        def schema_path(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
            cursor.close()

    return database


class _Recorder:
    """Collect one process's latencies and outcome counters under a lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latencies: dict[str, list[float]] = {name: [] for name in _OPERATIONS}
        self.counts: Counter[str] = Counter()
        self.claimed: list[str] = []
        self.timeline: list[tuple[str, float, float]] = []

    def timed(self, name: str, started: float) -> None:
        milliseconds = (time.perf_counter() - started) * 1000
        with self.lock:
            self.latencies[name].append(milliseconds)
            self.timeline.append((name, time.time(), milliseconds))
            self.counts[name] += 1

    def count(self, name: str) -> None:
        with self.lock:
            self.counts[name] += 1


def _pause(rng: random.Random, think_ms: int) -> None:
    if think_ms:
        time.sleep(rng.uniform(0.5, 1.5) * think_ms / 1000)


def _work_task(
    db: Database, actor: str, task: Mapping[str, object], spec: AnnotatorSpec, record: _Recorder
) -> None:
    """Save the task several times, each save on the previous one's revision."""
    rng = random.Random(f"{spec.seed}:{actor}:{task['id']}")  # noqa: S311  # Think time only.
    previous = task.get("latest_revision_id")
    for step in range(SAVES_PER_TASK):
        _pause(rng, spec.think_ms)
        started = time.perf_counter()
        revision = run_action(
            db,
            "save_revision",
            {
                "task_id": task["id"],
                "previous_revision_id": previous,
                "annotation": {
                    "sample_id": task["sample_id"],
                    "annotator_id": actor,
                    "labels": ["cat" if step % 2 == 0 else "dog"],
                },
            },
            actor,
        )
        record.timed("save", started)
        previous = str(revision["id"])


def _annotator(db: Database, actor: str, spec: AnnotatorSpec, record: _Recorder) -> None:
    rng = random.Random(f"{spec.seed}:{actor}")  # noqa: S311  # Think time only.
    claimed = 0
    while time.time() < spec.deadline:
        started = time.perf_counter()
        try:
            task = run_action(db, "claim_task", {"project_id": spec.project_id}, actor)
        except NotFoundError:
            record.count("queue_empty")
            _pause(rng, max(spec.think_ms, 200))
            continue
        record.timed("next", started)
        with record.lock:
            record.claimed.append(str(task["id"]))
        claimed += 1
        try:
            _work_task(db, actor, task, spec, record)
            if claimed % ABANDON_EVERY == 0:
                record.count("abandoned")
                continue
            _pause(rng, spec.think_ms)
            started = time.perf_counter()
            run_action(db, "submit_task", {"task_id": task["id"]}, actor)
            record.timed("submit", started)
        except LeaseExpiredError:
            record.count("lease_lost_while_working")


def annotator_process(spec: AnnotatorSpec) -> None:
    """Run this process's virtual annotators to the shared deadline and write raw results."""
    database = _database(spec)
    record = _Recorder()
    errors: list[str] = []

    def guarded(actor: str) -> None:
        try:
            _annotator(database, actor, spec, record)
        except Exception as error:  # noqa: BLE001  # Reported as a failed virtual user.
            with record.lock:
                errors.append(f"{actor}: {type(error).__name__}: {error}")

    threads = [threading.Thread(target=guarded, args=(actor,)) for actor in spec.actors]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    (spec.root / f"b8-annotators-{spec.index}.json").write_text(
        json.dumps(
            {
                "latencies": record.latencies,
                "timeline": record.timeline,
                "counts": dict(record.counts),
                "claimed": record.claimed,
                "errors": errors,
            }
        )
    )
    database.engine.dispose()


def reaper_process(spec: AnnotatorSpec) -> None:
    """Act as one worker's reaper loop until shortly after the annotators stop."""
    database = _database(spec)
    released: list[str] = []
    passes = 0
    while time.time() < spec.deadline + 2 * REAPER_INTERVAL_SECONDS:
        result = reap_expired_leases(database)
        released.extend(result.assignment_ids)
        passes += 1
        time.sleep(REAPER_INTERVAL_SECONDS)
    (spec.root / f"b8-reaper-{spec.index}.json").write_text(
        json.dumps({"released": released, "passes": passes})
    )
    database.engine.dispose()


def _specs(
    context: Context, project_id: str, actors: tuple[str, ...], deadline: float
) -> list[AnnotatorSpec]:
    processes = min(context.config.workers, len(actors))
    return [
        AnnotatorSpec(
            database_url=SecretStr(context.db.engine.url.render_as_string(hide_password=False)),
            schema_name=context.schema_name,
            root=context.root,
            index=index,
            project_id=project_id,
            actors=actors[index::processes],
            deadline=deadline,
            think_ms=context.config.think_ms,
            seed=context.config.seed,
        )
        for index in range(processes)
    ]


def _launch(specs: list[AnnotatorSpec]) -> None:
    factory = multiprocessing.get_context("spawn")
    processes: list[BaseProcess] = [
        factory.Process(target=annotator_process, args=(spec,)) for spec in specs
    ]
    processes += [
        factory.Process(target=reaper_process, args=(specs[0].model_copy(update={"index": index}),))
        for index in range(REAPER_PROCESSES)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=specs[0].deadline - time.time() + 600)
            if process.exitcode != 0:
                message = f"B8 child process failed or timed out: exit={process.exitcode}"
                raise RuntimeError(message)
    finally:
        for process in processes:
            if process.pid is not None and process.is_alive():
                process.terminate()
                process.join(timeout=10)


def _collect(root: Path) -> tuple[dict[str, list[float]], Counter[str], list[str], list[str]]:
    latencies: dict[str, list[float]] = {name: [] for name in _OPERATIONS}
    counts: Counter[str] = Counter()
    claimed: list[str] = []
    errors: list[str] = []
    for path in sorted(root.glob("b8-annotators-*.json")):
        data = json.loads(path.read_text())
        for name in _OPERATIONS:
            latencies[name].extend(data["latencies"][name])
        counts.update(data["counts"])
        claimed.extend(data["claimed"])
        errors.extend(data["errors"])
    return latencies, counts, claimed, errors


def _by_minute(root: Path, started: float) -> dict[str, str]:
    """Report p95 per elapsed minute, so drift over the run is visible next to the totals."""
    buckets: dict[str, dict[int, list[float]]] = {name: {} for name in _OPERATIONS}
    for path in sorted(root.glob("b8-annotators-*.json")):
        for name, moment, milliseconds in json.loads(path.read_text())["timeline"]:
            minute = int((moment - started) // 60)
            buckets[name].setdefault(minute, []).append(milliseconds)
    return {
        f"p95_by_minute_{name}": " ".join(
            f"{minute + 1}:{summarize(values).p95_ms:.0f}"
            for minute, values in sorted(minutes.items())
        )
        for name, minutes in buckets.items()
    }


def _reaped(root: Path) -> tuple[list[str], int]:
    released: list[str] = []
    passes = 0
    for path in sorted(root.glob("b8-reaper-*.json")):
        data = json.loads(path.read_text())
        released.extend(data["released"])
        passes += data["passes"]
    return released, passes


def run(context: Context) -> ScenarioResult:
    """Seed, run annotators and reapers to the deadline, then verify exclusivity in the database."""
    scale = context.scale
    seconds = context.config.duration_seconds or (
        scale.duration_seconds if context.config.size == "S" else B8_SECONDS
    )
    users = context.config.virtual_users or scale.virtual_users
    tasks = max(scale.tasks, users * 4)
    actors = tuple(f"annotator-{index:03d}" for index in range(users))
    project_id = seed_project(context.db, tasks, LEASE_MINUTES)
    register_annotators(context.db, project_id, actors)
    check_resources(context)
    started = time.time()
    _launch(_specs(context, project_id, actors, started + seconds))
    elapsed = time.time() - started
    latencies, counts, claimed, errors = _collect(context.root)
    released, passes = _reaped(context.root)
    verified = claim_overlaps(context.db, project_id)
    return ScenarioResult(
        scenario="B8",
        counts={
            **{name: int(value) for name, value in counts.items()},
            **verified,
            "tasks": tasks,
            "virtual_users": len(actors),
            "client_claims": len(claimed),
            "reaper_released": len(released),
            "reaper_duplicate_releases": len(released) - len(set(released)),
            "reaper_passes": passes,
            "failed_virtual_users": len(errors),
        },
        metrics={
            "elapsed_seconds": round(elapsed, 3),
            "think_ms": context.config.think_ms,
            "saves_per_task": SAVES_PER_TASK,
            "lease_minutes": LEASE_MINUTES,
            "abandon_every": ABANDON_EVERY,
            "processes": min(context.config.workers, len(actors)),
            "operations_per_second": round(
                sum(len(values) for values in latencies.values()) / max(elapsed, 1e-9), 2
            ),
            **_by_minute(context.root, started),
        },
        latencies={name: summarize(values) for name, values in latencies.items()},
        fixture_sha256=fingerprint({"tasks": tasks, "users": len(actors), "seed": 23}),
        notes=(
            "next = claim_task prepare+execute; save = save_revision; submit = submit_task",
            "every 40th claimed task is abandoned unsubmitted so the 1-minute lease is reaped",
            *errors[:5],
        ),
    )
