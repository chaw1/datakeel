# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Consent binds both image stages without constructing a transcription backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Never

import pytest
import yaml

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.transcription_models import (
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
)
from datakeel.storage.kg_store import list_runs
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_preparation_freezes_visual_consent_without_transcription(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The image destination independently requires approval before any backend is created."""
    dataset = image_dataset(db, tmp_path)
    profile = TranscriptionProfile(
        id="visual",
        backend="vlm",
        mode="vlm",
        model="example-vision",
        base_url="https://vision.example/v1",
    )
    use_profile(monkeypatch, profile)

    def forbidden(*_args: object, **_kwargs: object) -> Never:
        pytest.fail("Transcription was constructed before authorization")

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", forbidden)
    plan = prepare_image(db, dataset)
    estimate = plan.impact.transcription_estimate
    assert plan.requires_approval
    assert estimate is not None
    assert estimate.target_host == "vision.example"
    assert estimate.images == 1
    assert estimate.image_tokens == 22
    assert estimate.cost_upper_usd is None
    assert plan.impact.kg_estimate is not None
    assert plan.impact.kg_estimate.extraction_input_basis == "transcription_limit"
    assert plan.impact.kg_estimate.input_tokens >= profile.max_output_tokens
    with pytest.raises(AuthorizationError, match="human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db) == ()


def test_changed_transcription_recording_fails_before_model_execution(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing replay bytes cannot reuse an accepted plan even when image pixels match."""
    dataset = image_dataset(db, tmp_path)
    recording = TranscriptionRecording(
        model="scripted",
        recorded_at="2026-10-25",
        prompt_version="image-transcription-v1",
        source="Generated consent fixture",
        records=(
            TranscriptionRecord(**transcript().model_dump(), image_hash=dataset.files[0].sha256),
        ),
    )
    path = tmp_path / "transcription.yaml"
    path.write_text(yaml.safe_dump(recording.model_dump(mode="json")))
    profile = TranscriptionProfile(
        id="replay-fixture", backend="replay", model="scripted", recording=str(path)
    )
    use_profile(monkeypatch, profile)
    adapter = install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    path.write_text(path.read_text() + "\n# changed approved bytes\n")
    run = execute_graph(db, plan)
    assert run.status == "failed"
    assert run.report.model_calls == 0
    assert adapter.calls == 0
    assert "fingerprints" in (run.report.error or "")


def test_mode_override_is_bound_and_invalid_image_routes_are_rejected(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-file explicit mode changes are digest-bound and never silently become auto routing."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    first = prepare_image(db, dataset)
    second = prepare_image(db, dataset, mode_overrides={dataset.files[0].id: "vlm"})
    assert first.canonical_params["prepared"] != second.canonical_params["prepared"]
    with pytest.raises(ValidationError, match="selected image"):
        prepare_image(db, dataset, mode_overrides={"missing": "ocr"})
    use_profile(
        monkeypatch, TranscriptionProfile(id="ocr-fixture", backend="ocr", model="rapidocr")
    )
    with pytest.raises(ValidationError, match="ocr backend"):
        prepare_image(db, dataset, mode_overrides={dataset.files[0].id: "vlm"})


def test_transcription_budget_stop_creates_unexecuted_image_without_output(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A visual request cannot run with zero budget, even after its consent has been signed."""
    dataset = image_dataset(db, tmp_path)
    profile = TranscriptionProfile(
        id="visual",
        backend="vlm",
        mode="vlm",
        model="example-vision",
        base_url="http://127.0.0.1:8000/v1",
    )
    use_profile(monkeypatch, profile)
    transcriber = install_transcriber(monkeypatch, (transcript(),))
    extraction = install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset, budget_tokens=0))
    assert run.status == "budget_exceeded"
    assert run.report.unexecuted == 1
    assert run.report.transcriptions[0].status == "unexecuted"
    assert run.report.model_calls == 0
    assert len(transcriber.results) == 1
    assert extraction.calls == 0
