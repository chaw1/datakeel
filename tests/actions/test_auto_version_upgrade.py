# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persisted historical approvals and cached auto routes cannot authorize v2 work."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.policy import plan_digest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.errors import ValidationError
from datakeel.core.transcription_auto import AutoRoutingConfig
from datakeel.storage.action_rows import ActionPlanRow, ApprovalRow
from datakeel.storage.kg_image_sources import image_source
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import get_job, list_runs
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.storage.transcription_store import cached_transcription
from datakeel.transcription.cache import cache_key
from datakeel.transcription.factory import create_transcriber
from datakeel.worker.runner import run_worker
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.auto_helpers import install_visual, visual_profile
from tests.worker.image_helpers import image_dataset, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.core.transcription_models import TranscriptionMode, TranscriptionProfile
    from datakeel.storage.database import Database

_V2_FIELDS = {
    "strike_max_thickness_ratio",
    "strike_max_extension_ratio",
    "grey_alignment_height_ratio",
    "grey_max_line_height_ratio",
    "grey_max_neighbor_height_ratio",
    "grey_background_step_height_ratio",
    "grey_min_edge_concentration",
    "grey_edge_probe_height_ratio",
    "document_analysis_max_side",
    "document_padding_height_ratio",
    "document_min_contrast",
    "document_min_component_area_ratio",
}


def _historical_rules(profile: TranscriptionProfile) -> dict[str, JsonValue]:
    rules = profile.auto_routing.model_dump(mode="json", exclude=_V2_FIELDS)
    rules["version"] = "auto-v1"
    return rules


def _historical_profile_digest(profile: TranscriptionProfile) -> str:
    data = profile.model_dump(mode="json", exclude={"id", "recording", "api_key_env"})
    data["auto_routing"] = _historical_rules(profile)
    data["recording_hash"] = None
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _historical_cache_key(image_hash: str, profile: TranscriptionProfile) -> str:
    fingerprint = _historical_profile_digest(profile)
    return hashlib.sha256(f"{image_hash}:{fingerprint}".encode()).hexdigest()


def test_historical_auto_approval_is_rejected_before_any_backend(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An intact, signed v1 plan remains invalid after the application policy upgrade."""
    profile = visual_profile(monkeypatch)
    dataset = image_dataset(db, tmp_path)
    ocr, requests = install_visual(monkeypatch, {dataset.files[0].sha256: 0.99})
    plan = prepare_image(db, dataset)
    params = plan.model_dump(mode="json")["canonical_params"]
    params["prepared"]["transcription_profile"]["auto_routing"] = _historical_rules(profile)
    for document in params["prepared"]["documents"]:
        document["image"]["profile_digest"] = _historical_profile_digest(profile)
    historical = plan.model_copy(update={"canonical_params": params})
    historical = historical.model_copy(update={"plan_digest": plan_digest(historical)})
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        row.payload = historical.model_dump(mode="json")
        row.status = "APPROVED"
        session.add(
            ApprovalRow(
                plan_id=plan.id,
                plan_digest=historical.plan_digest,
                actor=plan.actor,
                status="APPROVED",
            )
        )
        session.commit()
    assert plan_digest(historical) == historical.plan_digest
    with pytest.raises(ValidationError, match="auto-v2"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=historical.plan_digest))
    assert not list_runs(db)
    assert ocr.calls == 0
    assert not requests
    with db.session() as session:
        approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id))
        assert approval is not None
        assert not approval.consumed


def test_historical_auto_cache_does_not_skip_current_worker_routing(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker ignores a real stored v1 visual handoff and computes a fresh local route."""
    profile = visual_profile(monkeypatch)
    dataset = image_dataset(db, tmp_path)
    image_hash = dataset.files[0].sha256
    historical_key = _historical_cache_key(image_hash, profile)
    assert historical_key != cache_key(image_hash, profile)
    previous = transcript("Historical route should not be reused.").model_dump(mode="json")
    previous["mode"] = "vlm"
    previous["auto_decision"] = {
        "route": "vlm",
        "reasons": ["struck_or_greyed_rows"],
        "version": "auto-v1",
    }
    with db.session() as session:
        session.add(TranscriptionRow(key=historical_key, payload=previous))
        session.commit()
    old_cached = cached_transcription(db, historical_key)
    assert old_cached is not None
    assert old_cached.auto_decision is not None
    assert old_cached.auto_decision.version == "auto-v1"
    ocr, requests = install_visual(monkeypatch, {image_hash: 0.99})
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "completed"
    result = run.report.transcriptions[0]
    assert not result.cached
    assert result.mode == "ocr"
    assert result.reasons == ("clean_text",)
    assert ocr.calls == 1
    assert not requests
    with db.session() as session:
        fresh = session.get(TranscriptionRow, cache_key(image_hash, profile))
        assert fresh is not None
        assert fresh.payload["auto_decision"]["version"] == "auto-v2"


def _historical_profile(profile: TranscriptionProfile) -> TranscriptionProfile:
    return profile.model_copy(
        update={"auto_routing": AutoRoutingConfig.model_validate(_historical_rules(profile))}
    )


def test_historical_run_and_source_remain_readable_beside_current_run(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved v1 prepared profile cannot hide any historical or current run/source view."""
    profile = visual_profile(monkeypatch)
    dataset = image_dataset(db, tmp_path)
    install_visual(monkeypatch, {dataset.files[0].sha256: 0.99})
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    old_run = execute_graph(db, plan)
    with db.session() as session:
        row = session.get(KGRunRow, old_run.id)
        assert row is not None
        payload = deepcopy(row.payload)
        payload["prepared"]["transcription_profile"]["auto_routing"] = _historical_rules(profile)
        row.payload = payload
        session.commit()
    new_plan = prepare_image(db, dataset)
    approve_plan(db, new_plan.id, ApprovalDecision(approve=True, plan_digest=new_plan.plan_digest))
    new_run = execute_graph(db, new_plan)
    assert {item.id for item in list_runs(db)} == {old_run.id, new_run.id}
    old_job = get_job(db, old_run.id)
    assert old_job.prepared.transcription_profile is not None
    assert old_job.prepared.transcription_profile.auto_routing.version == "auto-v1"
    document = old_job.documents[0]
    assert document.asset_ref.version is not None
    source = image_source(db, document.asset_ref.asset_id, document.asset_ref.version, old_run.id)
    assert source is not None
    assert source.text == "Acme uses Widget."


def test_historical_queued_job_is_rejected_before_transcription(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already queued legacy work fails with a readable report before any backend executes."""
    profile = visual_profile(monkeypatch)
    dataset = image_dataset(db, tmp_path)
    ocr, requests = install_visual(monkeypatch, {dataset.files[0].sha256: 0.99})
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    action = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    run = next(item for item in list_runs(db) if item.task_id == action.task_id)
    with db.session() as session:
        row = session.get(KGRunRow, run.id)
        assert row is not None
        payload = deepcopy(row.payload)
        payload["prepared"]["transcription_profile"]["auto_routing"] = _historical_rules(profile)
        row.payload = payload
        session.commit()
    run_worker(db, once=True)
    final = get_job(db, run.id).run
    assert final.status == "failed"
    assert "auto-v2" in (final.report.error or "")
    assert ocr.calls == 0
    assert not requests


@pytest.mark.parametrize("mode", ["ocr", "vlm"])
def test_historical_profile_allows_explicit_routes(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: TranscriptionMode
) -> None:
    """Explicit overrides preserve v1 profile compatibility without enabling legacy auto."""
    profile = _historical_profile(visual_profile(monkeypatch))
    use_profile(monkeypatch, profile)
    dataset = image_dataset(db, tmp_path)
    ocr, requests = install_visual(monkeypatch, {dataset.files[0].sha256: 0.99})
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset, transcription_mode=mode)
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "completed"
    assert run.report.transcriptions[0].mode == mode
    assert ocr.calls == 1
    assert len(requests) == (1 if mode == "vlm" else 0)


def test_historical_auto_profile_rejected_by_preparation_and_factory(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Typed legacy profiles stay readable but cannot prepare or construct new auto execution."""
    profile = _historical_profile(visual_profile(monkeypatch))
    use_profile(monkeypatch, profile)
    dataset = image_dataset(db, tmp_path)
    ocr, requests = install_visual(monkeypatch, {dataset.files[0].sha256: 0.99})
    with pytest.raises(ValidationError, match="auto-v2"):
        prepare_image(db, dataset)
    with pytest.raises(ValidationError, match="auto-v2"), create_transcriber(profile):
        pytest.fail("An obsolete automatic policy constructed a backend")
    assert ocr.calls == 0
    assert not requests
