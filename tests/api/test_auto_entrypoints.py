# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP discovery and preparation freeze automatic routes without executing transcription."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ActionPlan
from datakeel.actions.service import list_runs
from datakeel.api.app import create_app
from datakeel.core.transcription_auto import AutoRoutingConfig
from datakeel.core.transcription_models import TranscriptionProfile
from tests.asgi_client import TestClient
from tests.worker.image_helpers import image_dataset, use_profile

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from tests.kg.integration_helpers import TextDataset


def block_transcription_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail if preparation constructs a transcriber, runs OCR, or reads a visual credential."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Preparation accessed a transcription backend or model credential")

    for target in (
        "datakeel.transcription.factory.create_transcriber",
        "datakeel.worker.kg_transcription.create_transcriber",
        "datakeel.transcription.adapters.FakeTranscriber.transcribe",
        "datakeel.transcription.adapters.ReplayTranscriber.transcribe",
        "datakeel.transcription.ocr.RapidOCRTranscriber.transcribe",
        "datakeel.transcription.factory.VLMTranscriber.transcribe",
        "datakeel.transcription.auto_adapter.AutoTranscriber.transcribe",
        "datakeel.transcription.factory.get_settings",
    ):
        monkeypatch.setattr(target, forbidden)


def auto_profile(monkeypatch: pytest.MonkeyPatch) -> TranscriptionProfile:
    """Use an external fixture endpoint as a string only, with custom signed thresholds."""
    return use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="fixture-auto",
            backend="vlm",
            mode="vlm",
            model="scripted-auto-fixture",
            base_url="https://vision.example/v1",
            auto_routing=AutoRoutingConfig(min_mean_confidence=0.91),
        ),
    )


def assert_frozen_auto_plan(
    plan: ActionPlan, dataset: TextDataset, profile: TranscriptionProfile
) -> None:
    """Inspect the actual prepared snapshot and its complete worst-case outbound envelope."""
    params = RunKGExtractionParams.model_validate(plan.canonical_params)
    assert params.transcription_mode == "auto"
    prepared = params.prepared
    assert prepared is not None
    assert prepared.transcription_profile is not None
    assert prepared.transcription_profile.auto_routing == profile.auto_routing
    assert prepared.transcription_profile.auto_routing.version == "auto-v2"
    modes = {
        document.asset_ref.asset_id: document.image.mode
        for document in prepared.documents
        if document.image is not None
    }
    assert modes == {
        dataset.files[0].id: "auto",
        dataset.files[1].id: "ocr",
        dataset.files[2].id: "vlm",
    }
    estimate = prepared.transcription_estimate
    assert estimate is not None
    assert estimate.images == 3
    assert estimate.auto_images == 1
    assert {item.file_id for item in estimate.possible_external_images} == {
        dataset.files[0].id,
        dataset.files[2].id,
    }
    assert plan.external
    assert plan.requires_approval
    assert plan.status == "PREPARED"
    assert all(not document.blocks for document in prepared.documents)


def test_http_auto_schema_and_prepare_preserve_per_image_overrides_without_backends(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP discovery, schema validation and preparation support the same auto request."""
    dataset = image_dataset(db, tmp_path, count=3)
    profile = auto_profile(monkeypatch)
    block_transcription_backends(monkeypatch)
    arguments = {
        "dataset_id": dataset.dataset_id,
        "version_id": dataset.version_id,
        "profile_id": "fake",
        "transcription_profile_id": profile.id,
        "transcription_mode": "auto",
        "mode_overrides": {dataset.files[1].id: "ocr", dataset.files[2].id: "vlm"},
    }
    with TestClient(create_app(db)) as client:
        ontology = client.get("/api/ontology").json()
        contract = next(item for item in ontology["actions"] if item["id"] == "run_kg_extraction")
        schema = contract["params_schema"]
        assert schema["properties"]["transcription_mode"]["anyOf"][0]["enum"] == [
            "ocr",
            "vlm",
            "auto",
        ]
        assert schema["properties"]["mode_overrides"]["additionalProperties"]["enum"] == [
            "ocr",
            "vlm",
            "auto",
        ]
        Draft202012Validator(schema).validate(arguments)
        openapi = client.get("/api/openapi.json").json()
        assert (
            "auto"
            in openapi["components"]["schemas"]["TranscriptionProfile"]["properties"]["mode"][
                "enum"
            ]
        )
        response = client.post("/api/actions/run_kg_extraction/prepare", json=arguments)
        assert response.status_code == 200, response.text
        plan = ActionPlan.model_validate(response.json())
        assert_frozen_auto_plan(plan, dataset, profile)
        assert client.get(f"/api/actions/plans/{plan.id}").json() == response.json()
    assert list_runs(db) == []


def test_http_auto_rejects_an_override_outside_selected_images(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public HTTP boundary cannot attach an override to an unfrozen image identity."""
    dataset = image_dataset(db, tmp_path)
    profile = auto_profile(monkeypatch)
    block_transcription_backends(monkeypatch)
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/actions/run_kg_extraction/prepare",
            json={
                "dataset_id": dataset.dataset_id,
                "version_id": dataset.version_id,
                "profile_id": "fake",
                "transcription_profile_id": profile.id,
                "transcription_mode": "auto",
                "mode_overrides": {"unselected-image": "ocr"},
            },
        )
    assert response.status_code == 422
    assert "must refer to selected image file IDs" in response.json()["detail"]
    assert list_runs(db) == []
