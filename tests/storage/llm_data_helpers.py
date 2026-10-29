# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local training fixtures with independently known cleaning decisions."""

import json
from pathlib import Path

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.llm_data_governance import TrainingAnalysisRequest, TrainingGovernanceRun
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.llm_data_store import analyze_training


def seed_training(db: Database, directory: Path) -> tuple[str, Path, TrainingGovernanceRun]:
    """Create one valid line, its duplicate, a PII row and a malformed physical line."""
    path = directory / "training.jsonl"
    first = {"instruction": "Describe rainforests", "output": "Rainforests host diverse wildlife."}
    pii = {"instruction": "Where can we reach the fixture?", "output": "Write abc@example.test."}
    path.write_text(
        "\n".join(json.dumps(row) for row in (first, first, pii)) + "\nnot-json\n",
        encoding="utf-8",
    )
    untouched = directory / "keep.txt"
    untouched.write_text("Independent original file remains in the next version.")
    dataset = import_paths(db, "Training fixture", [path, untouched])
    report = analyze_training(db, dataset.id, TrainingAnalysisRequest())
    return dataset.id, path, report


def clean_training(db: Database, run: TrainingGovernanceRun) -> str:
    """Approve the real frozen action and return the actually published version identity."""
    plan = prepare_action(
        db, "clean_training_data", JsonDocument({"dataset_id": run.dataset_id, "run_id": run.id})
    )
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    executed = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert executed.receipt is not None
    return executed.receipt.outputs[0].asset_id
