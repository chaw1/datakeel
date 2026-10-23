# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for queue."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from datakeel.core.models import FileItem
from datakeel.storage.database import Database, EventRow, OutboxRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.datasets import import_dataset
from datakeel.worker.queue import DatabaseQueue

if TYPE_CHECKING:
    from pathlib import Path


def seed(db: Database, tmp_path: Path) -> str:
    """Provide the seed test fixture."""
    files = []
    for index in range(6):
        path = tmp_path / f"{index}.txt"
        path.write_text(f"Sample {index}")
        files.append(path)
    with db.session() as session:
        dataset = import_dataset(session, "queue-samples", files)
        session.commit()
        return dataset.id


def test_concurrent_claims_fenced_completion_and_outbox(db: Database, tmp_path: Path) -> None:
    """Verify concurrent claims fenced completion and outbox."""
    identifier = seed(db, tmp_path)
    queue = DatabaseQueue(db)
    task_id = queue.submit(identifier, "parallel", shards=6)
    assert queue.submit(identifier, "parallel", shards=6) == task_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda _: queue.claim(), range(6)))
    assert all(leases)
    assert len({lease.shard_id for lease in leases}) == 6
    assert queue.claim() is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda lease: queue.finish(
                    lease, [FileItem.model_validate(v) for v in lease.inputs], []
                ),
                leases,
            )
        )
    assert all(results)
    assert not queue.finish(leases[0], [], [])
    assert queue.relay() == 1
    assert queue.relay() == 0
    with db.session() as session:
        assert session.get(TaskRow, task_id).state == "COMPLETED"
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 2
        assert session.scalar(select(OutboxRow)).delivered
        assert session.scalar(select(func.count()).select_from(EventRow)) == 2


def test_reaper_rejects_old_lease_and_exhaustion_emits_terminal(
    db: Database, tmp_path: Path
) -> None:
    """Verify reaper rejects old lease and exhaustion emits terminal."""
    identifier = seed(db, tmp_path)
    queue = DatabaseQueue(db, lease_seconds=0.01, max_attempts=2)
    task_id = queue.submit(identifier, "reaper")
    old = queue.claim()
    with db.session() as session:
        session.get(ShardRow, old.shard_id).heartbeat_at = time.time() - 60
        session.commit()
    assert queue.reap() == 1
    new = queue.claim()
    assert new.owner != old.owner
    assert not queue.heartbeat(old)
    assert not queue.finish(old, [], [])
    assert queue.heartbeat(new)
    with db.session() as session:
        session.get(ShardRow, new.shard_id).heartbeat_at = time.time() - 60
        session.commit()
    assert queue.reap() == 1
    assert queue.relay() == 1
    with db.session() as session:
        assert session.get(TaskRow, task_id).state == "FAILED"


def test_explicit_input_version_freezes_selected_manifest(db: Database, tmp_path: Path) -> None:
    """Verify explicit input version freezes selected manifest."""
    identifier = seed(db, tmp_path)
    with db.session() as session:
        original = session.scalar(select(VersionRow).where(VersionRow.dataset_id == identifier))
        version = VersionRow(dataset_id=identifier, manifest=original.manifest[:2])
        session.add(version)
        session.commit()
        version_id = version.id
    queue = DatabaseQueue(db)
    task_id = queue.submit(identifier, "specific-version", version_id=version_id)
    lease = queue.claim()
    assert len(lease.inputs) == 2
    with db.session() as session:
        assert session.get(TaskRow, task_id).input_version_id == version_id


def test_concurrent_migrations_are_idempotent(db: Database) -> None:
    """Verify concurrent migrations are idempotent."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: db.migrate(), range(4)))


def test_existing_pipeline_without_default_fields_retains_idempotent_identity(
    db: Database, tmp_path: Path
) -> None:
    """Verify existing pipeline without default fields retains idempotent identity."""
    identifier = seed(db, tmp_path)
    pipeline = {
        "nodes": [{"id": "dedup", "operator": "file.dedup", "inputs": {"files": "$input.files"}}],
        "outputs": ["dedup.files"],
    }
    queue = DatabaseQueue(db)
    task_id = queue.submit(identifier, "legacy-shape", pipeline)
    with db.session() as session:
        session.get(TaskRow, task_id).pipeline = pipeline
        session.commit()
    assert queue.submit(identifier, "legacy-shape", pipeline) == task_id
