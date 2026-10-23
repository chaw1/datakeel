# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed real worker-extracted paired evidence for isolated golden conversations."""

from pathlib import Path

from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence.generator import generate_samples
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest
from datakeel.storage.task_queries import query_task
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute


def seed_evidence_case(db: Database, directory: Path) -> CaseFixture:
    """Generate twenty images and run the production DAG without importing gold observations."""
    samples = directory / "samples"
    generate_samples(samples, samples=20)
    (samples / "val/scene-0018/annotations.json").unlink()
    dataset = import_evidence_samples(db, "Generated evidence golden fixture", samples)
    queue = DatabaseQueue(db)
    identifier = queue.submit(dataset.id, "golden-evidence", evidence_pipeline())
    lease = queue.claim()
    if lease is None or not execute(queue, lease):
        msg = "Evidence fixture extraction could not acquire or complete its lease"
        raise ExecutionError(msg)
    task = query_task(db, identifier)
    if task.state != "COMPLETED":
        msg = f"Evidence fixture extraction {task.state}: {task.error or 'no failure detail'}"
        raise ExecutionError(msg)
    version, files = source_manifest(db, dataset.id)
    identifiers = {file.filename: file.id for file in files}
    return CaseFixture(
        dataset_id=dataset.id,
        file_id=identifiers["val/scene-0016/image.png"],
        unknown_file_id=identifiers["val/scene-0018/image.png"],
        version_id=version,
    )
