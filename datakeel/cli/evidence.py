# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed the paired evidence scenario and verify its rebuildable projection."""

from rich.console import Console

from datakeel.core.models import new_id
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence import generate_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.evidence_import import import_evidence_samples
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.worker.queue import DatabaseQueue

EVIDENCE_DEMO_NAME = "Paired scenes · evidence demo"


def seed_evidence_demo(db: Database) -> tuple[str, str]:
    """Reuse the source dataset and submit a fresh, incrementally cached extraction."""
    dataset = next((value for value in list_datasets(db) if value.name == EVIDENCE_DEMO_NAME), None)
    if dataset is None:
        directory = data_dir() / "evidence-samples"
        generate_samples(directory, samples=1000)
        dataset = import_evidence_samples(db, EVIDENCE_DEMO_NAME, directory)
    task_id = DatabaseQueue(db).submit(dataset.id, f"demo:evidence:{new_id()}", evidence_pipeline())
    return dataset.id, task_id


def rebuild(db: Database, expected_hash: str | None = None) -> None:
    """Reconstruct assertions from verified bundle artifacts and print hash equality."""
    result = rebuild_evidence(db, expected_hash)
    Console().print(result.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
    if not result.matches:
        raise SystemExit(1)
