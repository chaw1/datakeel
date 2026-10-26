# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Consent and cache identities bind every frozen automatic-routing threshold."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Never

import pytest
import yaml

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.policy import plan_digest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.errors import ConflictError
from datakeel.core.transcription_auto import AutoRoutingConfig
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.kg_store import list_runs
from datakeel.transcription.cache import cache_key, profile_digest
from datakeel.transcription.loader import load_profile
from tests.worker.image_helpers import image_dataset, prepare_image, use_profile

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _profile() -> TranscriptionProfile:
    return TranscriptionProfile(
        id="auto-fixture",
        backend="vlm",
        mode="auto",
        model="fixture-vision",
        base_url="https://vision.example/v1",
    )


def _changed_value(value: object) -> str | int | float:
    if isinstance(value, str):
        # Simulate a historical policy in raw stored JSON; automatic execution rejects it.
        return "auto-v1"
    if isinstance(value, int):
        return value + 1
    assert isinstance(value, float)
    return value + 0.001


@pytest.mark.parametrize("field", list(AutoRoutingConfig.model_fields))
def test_auto_threshold_tampering_invalidates_signed_plan(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    """An approval cannot authorize a changed threshold or a different policy version."""
    profile = use_profile(monkeypatch, _profile())
    dataset = image_dataset(db, tmp_path)
    plan = prepare_image(db, dataset)
    frozen = plan.canonical_params["prepared"]
    assert isinstance(frozen, dict)
    frozen_profile = frozen["transcription_profile"]
    assert isinstance(frozen_profile, dict)
    assert frozen_profile["auto_routing"] == profile.auto_routing.model_dump(mode="json")
    assert plan.requires_approval
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        payload = deepcopy(row.payload)
        rules = payload["canonical_params"]["prepared"]["transcription_profile"]["auto_routing"]
        rules[field] = _changed_value(rules[field])
        row.payload = payload
        session.commit()
    changed_params = deepcopy(plan.canonical_params)
    changed = changed_params["prepared"]
    assert isinstance(changed, dict)
    changed_profile = changed["transcription_profile"]
    assert isinstance(changed_profile, dict)
    changed_rules = changed_profile["auto_routing"]
    assert isinstance(changed_rules, dict)
    changed_rules[field] = _changed_value(changed_rules[field])
    assert (
        plan_digest(plan.model_copy(update={"canonical_params": changed_params}))
        != plan.plan_digest
    )
    with pytest.raises(ConflictError, match="plan_digest"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db) == ()


@pytest.mark.parametrize("field", list(AutoRoutingConfig.model_fields))
def test_auto_profile_and_cache_include_every_rule_field(field: str) -> None:
    """Any rule edit gives automatic results a new identity; explicit routes preserve theirs."""
    profile = _profile()
    original = profile.auto_routing.model_dump()
    changed_config = profile.auto_routing.model_copy(
        update={field: _changed_value(original[field])}
    )
    changed = profile.model_copy(update={"auto_routing": changed_config})
    image_hash = "f" * 64
    assert profile_digest(profile) != profile_digest(changed)
    assert cache_key(image_hash, profile) != cache_key(image_hash, changed)
    for mode in ("ocr", "vlm"):
        assert profile_digest(profile, mode=mode) == profile_digest(changed, mode=mode)
        assert cache_key(image_hash, profile, mode=mode) == cache_key(
            image_hash, changed, mode=mode
        )


def test_auto_preparation_never_runs_ocr_vision_or_routing(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consent discloses the entire possible image envelope without observing local OCR."""
    use_profile(monkeypatch, _profile())
    dataset = image_dataset(db, tmp_path, count=3)

    def forbidden(*_args: object, **_kwargs: object) -> Never:
        pytest.fail("A transcription backend, rule, or credential was reached during preparation")

    for target in (
        "datakeel.transcription.ocr.RapidOCRTranscriber.transcribe",
        "datakeel.transcription.factory.VLMTranscriber.transcribe",
        "datakeel.transcription.auto.decide_auto_route",
        "datakeel.transcription.auto_adapter.decide_auto_route",
        "datakeel.worker.kg_transcription.create_transcriber",
        "datakeel.core.settings.Settings.extraction_key",
    ):
        monkeypatch.setattr(target, forbidden)
    plan = prepare_image(db, dataset)
    estimate = plan.impact.transcription_estimate
    assert plan.requires_approval
    assert estimate is not None
    assert estimate.auto_images == 3
    assert {item.file_id for item in estimate.possible_external_images} == {
        file.id for file in dataset.files
    }
    assert all(item.mode == "auto" for item in estimate.possible_external_images)
    assert list_runs(db) == ()


def test_auto_profile_yaml_overrides_routing_configuration(tmp_path: Path) -> None:
    """Users can tune thresholds in the same typed profile covered by approval fingerprints."""
    profile = _profile()
    configuration = profile.model_dump(mode="json")
    configuration["auto_routing"] = {"min_mean_confidence": 0.9, "strike_min_width_ratio": 0.8}
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(configuration))
    loaded = load_profile(path)
    assert loaded.auto_routing.min_mean_confidence == 0.9
    assert loaded.auto_routing.strike_min_width_ratio == 0.8
    assert loaded.auto_routing.version == "auto-v2"
