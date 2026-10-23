# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute the offline benchmark inside a process with only explicit local settings."""

import argparse
from pathlib import Path
from time import perf_counter

from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_eval import EvidenceEvalReport
from datakeel.harness.evidence_evaluation import evaluate_evidence_dataset
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence import generate_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.evidence_import import import_evidence_samples
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute


def run_benchmark(
    db: Database, directory: Path, questions: Path | None = None, *, samples: int = 1000
) -> EvidenceEvalReport:
    """Generate a fresh corpus and run the production worker before measuring its observations."""
    started = perf_counter()
    generate_samples(directory, samples=samples)
    dataset = import_evidence_samples(db, "Generated evidence benchmark", directory)
    queue = DatabaseQueue(db)
    task = queue.submit(dataset.id, "evidence-benchmark", evidence_pipeline())
    lease = queue.claim()
    if lease is None or lease.task_id != task or not execute(queue, lease):
        msg = "Fresh evidence benchmark extraction did not complete"
        raise ExecutionError(msg)
    report = evaluate_evidence_dataset(
        db, dataset.id, directory / "gold.json", task, questions, extraction_scope="fresh"
    )
    return report.model_copy(update={"benchmark_seconds": perf_counter() - started})


def main() -> None:
    """Write the internal subprocess result to a parent-owned temporary JSON artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--questions", type=Path)
    args = parser.parse_args()
    db = Database()
    db.migrate()
    try:
        result = run_benchmark(db, data_dir() / "samples", args.questions)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
