# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small real extraction fixtures shared by evidence interfaces and queries."""

from pathlib import Path

from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence.generator import generate_samples
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import import_evidence_samples
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute


def seed_query_evidence(db: Database, directory: Path) -> str:
    """Extract twenty local samples including corruption and missing annotations."""
    generate_samples(directory, samples=20)
    (directory / "val/scene-0019/image.png").write_bytes(b"unreadable generated image")
    (directory / "val/scene-0018/annotations.json").unlink()
    dataset = import_evidence_samples(db, "evidence interface samples", directory)
    queue = DatabaseQueue(db)
    queue.submit(dataset.id, f"evidence-interface:{dataset.id}", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    return dataset.id
