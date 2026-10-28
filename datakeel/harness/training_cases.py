# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate independent local training records for real read-tool golden observations."""

from pathlib import Path

from datakeel.core.harness_eval import CaseFixture
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths


def seed_training_case(db: Database, directory: Path) -> CaseFixture:
    """Include a malformed line and duplicate without any external benchmark content."""
    path = directory / "generated-training.jsonl"
    record = '{"instruction":"Explain reusable local fixtures","output":"They isolate tests."}'
    path.write_text(f"{record}\n{record}\ninvalid-json\n", encoding="utf-8")
    dataset = import_paths(db, "Generated training governance fixture", [path])
    return CaseFixture(dataset_id=dataset.id, file_id="")
