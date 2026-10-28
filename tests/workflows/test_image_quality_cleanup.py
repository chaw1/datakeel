# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The bundled cleanup workflow consumes measured image facts without version overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageFilter

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, get_plan, list_runs, prepare_action
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.pipeline.image_pointcloud import image_pointcloud_pipeline
from datakeel.runtime.workflow_service import resume_workflow, start_workflow
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.actions.models import ActionPlan
    from datakeel.core.workflow_models import WorkflowRun
    from datakeel.storage.database import Database


def _measured_images(db: Database, directory: Path) -> tuple[str, str]:
    y, x = np.indices((384, 512))
    gray = np.where((x // 16 + y // 16) % 2, 56, 200).astype(np.uint8)
    image = Image.fromarray(np.repeat(gray[..., None], 3, axis=2))
    high, low = directory / "sharp.png", directory / "blurred.png"
    image.save(high)
    image.filter(ImageFilter.GaussianBlur(7)).save(low)
    dataset = import_paths(db, "image-workflow-cleanup", [high, low])
    low_id = next(item.id for item in list_files(db, dataset.id) if item.filename == "blurred.png")
    plan = prepare_action(
        db,
        "run_pipeline",
        JsonDocument.model_validate(
            {
                "dataset_id": dataset.id,
                "pipeline": image_pointcloud_pipeline().model_dump(mode="json"),
            }
        ),
    )
    queued = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run_worker(db, once=True)
    assert next(item for item in list_runs(db) if item.id == queued.id).status == "SUCCEEDED"
    return dataset.id, low_id


def _pause(db: Database, dataset_id: str) -> tuple[WorkflowRun, ActionPlan]:
    run = list(
        start_workflow(
            db,
            "low-quality-cleanup",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset_id, "quality_max": 60}),
                idempotency_key="measured-image-cleanup",
            ),
        )
    )[-1].run
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    return run, get_plan(db, run.pending_plan_id)


def test_bundled_cleanup_uses_measured_images_without_version_override(
    db: Database, tmp_path: Path
) -> None:
    """Find the low image through the unchanged template and enforce its signed resume gate."""
    dataset_id, low_id = _measured_images(db, tmp_path)
    run, plan = _pause(db, dataset_id)
    assert plan.action_type == "delete_files"
    assert [item.asset_ref.asset_id for item in plan.manifest.objects] == [low_id]
    assert plan.manifest.objects[0].properties["quarantined"] is True
    files = list_files(db, dataset_id)
    assert {item.filename for item in files} == {"sharp.png", "blurred.png"}
    healthy = next(item for item in files if item.filename == "sharp.png")
    assert healthy.metadata.get("quarantined", False) is False
    with pytest.raises(AuthorizationError, match="approval"):
        list(resume_workflow(db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="unsigned")))
    assert {item.filename for item in list_files(db, dataset_id)} == {"sharp.png", "blurred.png"}
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    completed = list(
        resume_workflow(db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="signed"))
    )[-1].run
    assert completed.status == "SUCCEEDED"
    assert [item.filename for item in list_files(db, dataset_id)] == ["sharp.png"]


def test_bundled_image_cleanup_rejection_preserves_original_files(
    db: Database, tmp_path: Path
) -> None:
    """Reject deletion after the original workflow quarantines only the low-scored source."""
    dataset_id, low_id = _measured_images(db, tmp_path)
    run, plan = _pause(db, dataset_id)
    assert [item.asset_ref.asset_id for item in plan.manifest.objects] == [low_id]
    rejected = approve_plan(
        db,
        plan.id,
        ApprovalDecision(approve=False, plan_digest=plan.plan_digest, reason="Keep source image"),
    )
    assert rejected.status == "REJECTED"
    with pytest.raises(AuthorizationError, match="approval"):
        list(resume_workflow(db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="rejected")))
    assert {item.filename for item in list_files(db, dataset_id)} == {"sharp.png", "blurred.png"}
