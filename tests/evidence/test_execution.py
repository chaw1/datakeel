# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Worker-integrated incremental execution, cache accounting, and fenced publication."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PIL import Image
from sqlalchemy import select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.evidence_models import EvidenceValue, ImageRegion
from datakeel.evidence.execution import EvidenceExecution
from datakeel.operators.evidence import annotation_labels, image_phash
from datakeel.operators.evidence.facts import ImageDimensions
from datakeel.pipeline import run_pipeline
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence.generator import generate_samples
from datakeel.storage.database import EventRow, ShardRow, TaskRow
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.pipeline.models import Pipeline
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


def _run(db: Database, dataset_id: str, name: str, pipeline: Pipeline) -> str:
    queue = DatabaseQueue(db)
    task = queue.submit(dataset_id, name, pipeline)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    return task


def _person_box(db: Database, asset_id: str) -> tuple[tuple[float, ...], int, int]:
    (region,) = (
        anchor.selector
        for assertion in list_assertions(db, asset_id)
        if assertion.predicate == "annotated_as"
        and isinstance(assertion.object, EvidenceValue)
        and assertion.object.concept == "person"
        for anchor in assertion.anchors
        if isinstance(anchor.selector, ImageRegion)
    )
    return region.bbox, region.width, region.height


def test_upgrade_re_extracts_stored_frame_boxes_instead_of_reusing_v0_18_cache(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A v0.18.0 run cached stored-frame boxes at 1.0; the current preset must not reuse them."""
    directory = tmp_path / "samples"
    generate_samples(directory, samples=20)
    scene = directory / "train/scene-0000"
    with Image.open(scene / "image.png") as image:
        stored = image.copy()
    exif = Image.Exif()
    exif[274] = 6
    stored.save(scene / "image.png", exif=exif)
    sidecar = (
        '{"annotations":[{"category":"person","bbox":[24,28,48,72]}],"width":192,"height":128}'
    )
    (scene / "annotations.json").write_text(sidecar, encoding="utf-8")
    dataset_id = import_evidence_samples(db, "upgraded samples", directory).id
    rotated = next(
        item.id
        for item in source_manifest(db, dataset_id)[1]
        if str(item.metadata["evidence_sample"]["sample_key"]).startswith("train/scene-0000/")
    )
    with monkeypatch.context() as legacy:
        # v0.18.0 measured and framed boxes on stored pixels and pinned every extractor to 1.0.
        legacy.setattr(annotation_labels, "_geometry", lambda _file: None)
        legacy.setattr(
            image_phash,
            "_upright_size",
            lambda image: ImageDimensions(width=image.width, height=image.height),
        )
        preset = evidence_pipeline()
        old = preset.model_copy(
            update={
                "nodes": [
                    node.model_copy(update={"params": {"extractor_version": "1.0"}})
                    if node.operator
                    else node
                    for node in preset.nodes
                ]
            }
        )
        _run(db, dataset_id, "v0.18.0", old)
    assert _person_box(db, rotated) == ((24, 28, 72, 100), 192, 128)
    assert rebuild_evidence(db).matches
    assert _person_box(db, rotated) == ((24, 28, 72, 100), 192, 128), "replay never re-extracts"
    report = extraction_report(db, _run(db, dataset_id, "upgraded", evidence_pipeline()))
    assert (report.extracted, report.skipped_cached) == (40, 60)
    assert _person_box(db, rotated) == ((28, 24, 100, 72), 128, 192)
    decisions = list_decisions(db)
    assert {entry.actor for entry in decisions} == {
        "evidence.image_phash",
        "evidence.annotation_labels",
    }
    assert {entry.reason for entry in decisions} == {"extractor_version_changed"}
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
