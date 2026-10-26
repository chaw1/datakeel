# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Automatic routes obey consent, budgets, overrides and durable report semantics."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.kg_execution import KGJob
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import list_runs
from datakeel.worker.runner import run_worker
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.auto_helpers import install_visual, visual_profile
from tests.worker.image_helpers import image_dataset, prepare_image

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database


def _approve(db: Database, plan: ActionPlan) -> None:
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))


def test_auto_only_sends_low_confidence_image_and_preserves_reference(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The signed worst-case envelope overestimates actual transfers and charges."""
    dataset = image_dataset(db, tmp_path, 2)
    visual_profile(monkeypatch)
    ocr, requests = install_visual(
        monkeypatch,
        {
            dataset.files[0].sha256: 0.99,
            dataset.files[1].sha256: 0.25,
        },
    )
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    plan = prepare_image(db, dataset)
    assert not ocr.calls
    assert not requests
    estimate = plan.impact.transcription_estimate
    assert estimate is not None
    assert estimate.auto_images == 2
    assert len(estimate.possible_external_images) == 2
    assert estimate.cost_upper_usd is not None
    assert estimate.cost_upper_usd > 0
    _approve(db, plan)
    run = execute_graph(db, plan)
    assert run.status == "completed"
    local, visual = run.report.transcriptions
    assert local.mode == "ocr"
    assert local.reasons == ("clean_text",)
    assert not local.external
    assert visual.mode == "vlm"
    assert "low_confidence" in visual.reasons
    assert visual.external
    assert visual.ocr_reference is not None
    assert visual.ocr_reference.text == "Acme uses Widget."
    assert len(requests) == 1
    assert ocr.calls == 2
    assert run.report.transcription_external_images == 1
    assert run.report.transcription_cost_usd == Decimal("0.000024")
    assert run.report.transcription_cost_usd < estimate.cost_upper_usd
    repeated_plan = prepare_image(db, dataset)
    _approve(db, repeated_plan)
    repeated = execute_graph(db, repeated_plan)
    assert len(requests) == 1
    assert ocr.calls == 2
    assert all(item.cached and not item.external for item in repeated.report.transcriptions)
    assert repeated.report.transcription_external_images == 0
    assert repeated.report.transcription_cost_usd == 0


def test_auto_override_takes_precedence_and_changes_outbound_envelope(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One forced OCR image stays local despite low confidence; forced vision bypasses routing."""
    dataset = image_dataset(db, tmp_path, 2)
    visual_profile(monkeypatch)
    _, requests = install_visual(monkeypatch, {file.sha256: 0.1 for file in dataset.files})
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    plan = prepare_image(
        db,
        dataset,
        mode_overrides={
            dataset.files[0].id: "ocr",
            dataset.files[1].id: "vlm",
        },
    )
    estimate = plan.impact.transcription_estimate
    assert estimate is not None
    assert estimate.auto_images == 0
    assert [entry.file_id for entry in estimate.possible_external_images] == [dataset.files[1].id]
    _approve(db, plan)
    run = execute_graph(db, plan)
    assert [item.mode for item in run.report.transcriptions] == ["ocr", "vlm"]
    assert all(not item.reasons for item in run.report.transcriptions)
    assert len(requests) == 1


def test_auto_unlisted_image_fails_individually_before_transport(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing an authorized transfer from the worker envelope denies only that image."""
    dataset = image_dataset(db, tmp_path, 3)
    visual_profile(monkeypatch)
    _, requests = install_visual(monkeypatch, {file.sha256: 0.2 for file in dataset.files})
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    plan = prepare_image(db, dataset)
    _approve(db, plan)
    action = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run = next(run for run in list_runs(db) if run.task_id == action.task_id)
    with db.session() as session:
        row = session.get(KGRunRow, run.id)
        assert row is not None
        job = KGJob.model_validate(row.payload)
        estimate = job.prepared.transcription_estimate
        assert estimate is not None
        estimate = estimate.model_copy(
            update={"possible_external_images": estimate.possible_external_images[1:]}
        )
        prepared = job.prepared.model_copy(update={"transcription_estimate": estimate})
        row.payload = job.model_copy(update={"prepared": prepared}).model_dump(mode="json")
        session.commit()
    run_worker(db, once=True)
    final = next(item for item in list_runs(db) if item.id == run.id)
    assert final.status == "partial"
    assert final.report.transcription_failed == 1
    assert final.report.failures[0].reason == "transcription:outbound_not_approved"
    assert not final.report.transcriptions[0].external
    assert len(requests) == 2
    assert [item.status for item in final.report.transcriptions] == [
        "failed",
        "completed",
        "completed",
    ]


def test_auto_budget_zero_keeps_clean_text_and_blocks_visual_request(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Budget failure for a routed image does not prevent free OCR images from completing."""
    dataset = image_dataset(db, tmp_path, 2)
    visual_profile(monkeypatch)
    _, requests = install_visual(
        monkeypatch,
        {
            dataset.files[0].sha256: 0.99,
            dataset.files[1].sha256: 0.25,
        },
    )
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    plan = prepare_image(db, dataset, max_cost_usd="0")
    _approve(db, plan)
    run = execute_graph(db, plan)
    assert run.status == "budget_exceeded"
    assert not requests
    assert not list_traces(db, run.id)
    assert run.report.transcriptions[0].status == "completed"
    assert run.report.transcriptions[1].status == "unexecuted"
    assert not any(item.external for item in run.report.transcriptions)
