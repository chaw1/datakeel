# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Worker-integrated incremental execution, cache accounting, and fenced publication."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.evidence.execution import EvidenceExecution
from datakeel.pipeline import run_pipeline
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence.generator import generate_samples
from datakeel.storage.database import EventRow, ShardRow, TaskRow
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_import import import_evidence_samples
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def seed_evidence(db: Database, directory: Path, *, corrupt: bool = False) -> str:
    """Import synthetic paired samples without exposing gold to any runtime component."""
    generate_samples(directory, samples=20)
    if corrupt:
        (directory / "val/scene-0019/image.png").write_bytes(b"unreadable generated image")
    (directory / "val/scene-0018/annotations.json").unlink()
    return import_evidence_samples(db, "incremental samples", directory).id


def test_worker_first_run_cache_reuse_and_one_extractor_version_invalidation(
    db: Database,
    tmp_path: Path,
) -> None:
    """Cache all outcomes and invalidate only the extractor whose own version changed."""
    dataset_id = seed_evidence(db, tmp_path / "samples", corrupt=True)
    queue = DatabaseQueue(db)
    pipeline = evidence_pipeline()
    task = queue.submit(dataset_id, "first", pipeline)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    first = extraction_report(db, task)
    assert first.inputs == 100
    assert first.failed == 1
    assert first.extracted == first.inputs - first.failed
    assert first.skipped_cached == 0
    original = list_assertions(db)
    task = queue.submit(dataset_id, "cached", pipeline)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    cached = extraction_report(db, task)
    assert cached.skipped_cached == cached.inputs == 100
    assert cached.extracted == cached.failed == 0
    assert list_assertions(db) == original
    pipeline = pipeline.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"params": {"extractor_version": "2.0"}})
                if node.operator == "evidence.caption_mentions"
                else node
                for node in pipeline.nodes
            ]
        }
    )
    task = queue.submit(dataset_id, "changed-caption", pipeline)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    changed = extraction_report(db, task)
    assert changed.extracted == 20
    assert changed.skipped_cached == 80
    assert {entry.actor for entry in list_decisions(db)} == {"evidence.caption_mentions"}
    assert rebuild_evidence(db).matches


def test_lost_lease_cannot_publish_precomputed_assertions_or_cache(
    db: Database, tmp_path: Path
) -> None:
    """Keep all computed evidence uncommitted until the current fencing token is verified."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    queue = DatabaseQueue(db)
    task = queue.submit(dataset_id, "stale", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert lease.input_version_id is not None
    runtime = EvidenceExecution(
        db,
        EvidenceExecutionContext(
            task_id=task,
            shard_id=lease.shard_id,
            version_id=lease.input_version_id,
        ),
    )
    files = run_pipeline(
        materialize_files(lease.inputs),
        tmp_path / "output",
        lease.pipeline,
        operator_executor=runtime.execute_node,
    )
    assert runtime.pending
    assert not list_assertions(db)
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.lease_owner = "new-owner"
        session.commit()
    assert not queue.finish(lease, files, [], evidence=tuple(runtime.pending))
    assert not list_assertions(db)
    assert extraction_report(db, task).inputs == 0
    with db.session() as session:
        assert len(list(session.scalars(select(EventRow)))) == 1


def test_evidence_worker_retains_source_version_and_stores_only_bundle_references(
    db: Database,
    tmp_path: Path,
) -> None:
    """Bind all assertions to source manifests and preserve one COMPLETE per operator."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    queue = DatabaseQueue(db)
    task = queue.submit(dataset_id, "identity", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    assert {value.subject.version for value in list_assertions(db)} == {lease.input_version_id}
    with db.session() as session:
        events = [row.payload for row in session.scalars(select(EventRow))]
        produced = [event for event in events if event["source_module"] == "evidence"]
        assert len(produced) == 5
        assert all(event["event_type"] == "COMPLETE" for event in produced)
        assert all("assertions" not in str(event["params"]) for event in produced)
        completed = session.get(TaskRow, task)
        assert completed is not None
        assert completed.state == "COMPLETED"


def test_invalid_evidence_rolls_back_whole_fenced_completion(db: Database, tmp_path: Path) -> None:
    """Commit neither earlier node observations nor task output when any bundle is invalid."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    queue = DatabaseQueue(db)
    task = queue.submit(dataset_id, "invalid-publication", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert lease.input_version_id is not None
    runtime = EvidenceExecution(
        db,
        EvidenceExecutionContext(
            task_id=task,
            shard_id=lease.shard_id,
            version_id=lease.input_version_id,
        ),
    )
    files = run_pipeline(
        materialize_files(lease.inputs),
        tmp_path / "run",
        lease.pipeline,
        operator_executor=runtime.execute_node,
    )
    invalid = runtime.pending[-1].model_copy(
        update={"event": runtime.pending[-1].event.model_copy(update={"event_type": "FAILED"})}
    )
    with pytest.raises(ValidationError, match="COMPLETE"):
        queue.finish(lease, files, [], evidence=(*runtime.pending[:-1], invalid))
    assert not list_assertions(db)
    assert not list_decisions(db)
    with db.session() as session:
        task_row = session.get(TaskRow, task)
        assert task_row is not None
        assert task_row.state == "QUEUED"
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        assert shard.state == "RUNNING"
        assert shard.lease_owner == lease.owner
        assert len(list(session.scalars(select(EventRow)))) == 1
