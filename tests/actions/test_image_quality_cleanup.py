# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image measurements drive real frozen selections and the existing approval boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageFilter

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, list_runs, prepare_action
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import ObjectSet
from datakeel.pipeline import Node, Pipeline
from datakeel.storage.dataset_service import import_paths, list_files, list_versions
from datakeel.storage.object_queries import evaluate
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _measure_generated_dataset(db: Database, directory: Path) -> tuple[str, str]:
    y, x = np.indices((384, 512))
    gray = np.where((x // 16 + y // 16) % 2, 56, 200).astype(np.uint8)
    image = Image.fromarray(np.repeat(gray[..., None], 3, axis=2))
    high, low = directory / "sharp.png", directory / "blurred.png"
    image.save(high)
    image.filter(ImageFilter.GaussianBlur(7)).save(low)
    dataset = import_paths(db, "generated-image-cleanup", [high, low])
    definition = Pipeline(
        nodes=[
            Node(id="modality", kind="route", inputs={"files": "$input.files"}),
            Node(id="measure", operator="image.quality", inputs={"files": "modality.image"}),
        ],
        outputs=["measure.files"],
    )
    plan = prepare_action(
        db,
        "run_pipeline",
        JsonDocument.model_validate(
            {"dataset_id": dataset.id, "pipeline": definition.model_dump(mode="json")}
        ),
    )
    queued = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert queued.status == "QUEUED"
    run_worker(db, once=True)
    completed = next(run for run in list_runs(db) if run.id == queued.id)
    assert completed.status == "SUCCEEDED"
    measured = [
        version
        for version in list_versions(db, dataset.id)
        if all("image_quality" in item.metadata for item in version.manifest)
    ]
    assert len(measured) == 1
    return dataset.id, measured[0].id


def test_low_quality_images_require_approval_and_preserve_high_quality_samples(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freeze measured low-score images, quarantine them, and sign their deletion."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    dataset_id, version_id = _measure_generated_dataset(db, tmp_path)
    selection = ObjectSet(dataset_id=dataset_id, version_ids=[version_id], quality_max=60)
    selected = evaluate(db, selection)
    assert [item.properties["filename"] for item in selected.objects] == ["blurred.png"]
    assert selected.objects[0].properties["quality"] < 60
    healthy = evaluate(
        db, ObjectSet(dataset_id=dataset_id, version_ids=[version_id], quality_min=75)
    )
    assert [item.properties["filename"] for item in healthy.objects] == ["sharp.png"]
    params = JsonDocument.model_validate({"selection": selection.model_dump(mode="json")})
    quarantine = prepare_action(db, "quarantine_files", params)
    assert quarantine.requires_approval is False
    execute_plan(db, quarantine.id, ExecuteRequest(plan_digest=quarantine.plan_digest))
    assert len(list_files(db, dataset_id, version_id)) == 2
    deletion = prepare_action(db, "delete_files", params)
    assert deletion.requires_approval is True
    assert [item.properties["filename"] for item in deletion.manifest.objects] == ["blurred.png"]
    assert deletion.manifest.objects[0].properties["quarantined"] is True
    with pytest.raises(AuthorizationError, match="human approval"):
        execute_plan(db, deletion.id, ExecuteRequest(plan_digest=deletion.plan_digest))
    assert {item.filename for item in list_files(db, dataset_id, version_id)} == {
        "sharp.png",
        "blurred.png",
    }
    approve_plan(db, deletion.id, ApprovalDecision(approve=True, plan_digest=deletion.plan_digest))
    receipt = execute_plan(db, deletion.id, ExecuteRequest(plan_digest=deletion.plan_digest))
    assert receipt.status == "SUCCEEDED"
    assert [item.filename for item in list_files(db, dataset_id, version_id)] == ["sharp.png"]
    assert [item.filename for item in list_files(db, dataset_id)] == ["sharp.png"]


def test_rejected_image_cleanup_preserves_all_measured_files(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A human rejection leaves the measured low-score file and its healthy peer intact."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    dataset_id, version_id = _measure_generated_dataset(db, tmp_path)
    selection = ObjectSet(dataset_id=dataset_id, version_ids=[version_id], quality_max=60)
    plan = prepare_action(
        db,
        "delete_files",
        JsonDocument.model_validate({"selection": selection.model_dump(mode="json")}),
    )
    decision = approve_plan(
        db,
        plan.id,
        ApprovalDecision(approve=False, plan_digest=plan.plan_digest, reason="Keep generated data"),
    )
    assert decision.status == "REJECTED"
    assert {item.filename for item in list_files(db, dataset_id, version_id)} == {
        "sharp.png",
        "blurred.png",
    }
