# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Common real image prerequisites fail individually while unrelated sources finish."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from io import BytesIO
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.api.app import create_app
from datakeel.core.kg_queries import KGQuery
from datakeel.core.settings import Settings
from datakeel.core.transcription_models import (
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
)
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_queries import explain_relation, query_kg
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.factory import VLMTranscriber
from tests.kg.integration_helpers import TextDataset, execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import install_transcriber, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.storage.database import Database


def _mixed_dataset(db: Database, directory: Path, *, malformed: bool = False) -> TextDataset:
    paths = [directory / "first.png", directory / "second.png", directory / "text.txt"]
    Image.new("RGB", (200, 100), "white").save(paths[0])
    Image.new("RGB", (200, 100), "black").save(paths[1])
    if malformed:
        paths[0].write_bytes(b"invalid image bytes")
    paths[2].write_text("Acme uses Widget.")
    dataset = import_paths(db, "Mixed image failures", paths)
    version, files = source_manifest(db, dataset.id)
    return TextDataset(dataset_id=dataset.id, version_id=version, files=tuple(files))


def _replay_profile(dataset: TextDataset, path: Path, *, mismatch: bool) -> TranscriptionProfile:
    records = tuple(
        TranscriptionRecord(
            **transcript()
            .model_copy(update={"backend": "ocr" if file.filename == "first.png" else "vlm"})
            .model_dump(),
            image_hash=file.sha256 or "0" * 64,
        )
        for file in dataset.files
        if file.filename == "second.png" or (mismatch and file.filename == "first.png")
    )
    path.write_text(
        TranscriptionRecording(
            model="recorded",
            recorded_at="2026-10-25",
            prompt_version="image-transcription-v1",
            source="generated fixture",
            records=records,
        ).model_dump_json()
    )
    return TranscriptionProfile(
        id="partial-replay", backend="replay", mode="vlm", model="recorded", recording=str(path)
    )


@pytest.mark.parametrize("mismatch", [False, True])
def test_replay_when_record_missing_or_mode_mismatches_continues_other_sources(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mismatch: bool
) -> None:
    """Actual recordings drive failures, with no mocked exception from the transcriber."""
    dataset = _mixed_dataset(db, tmp_path)
    profile = _replay_profile(dataset, tmp_path / "recording.json", mismatch=mismatch)
    use_profile(monkeypatch, profile)
    extraction = install_adapter(monkeypatch, (pair_result(), pair_result()))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "partial"
    assert run.report.transcription_failed == 1
    assert run.report.failures[0].reason == (
        "transcription:mode_mismatch" if mismatch else "transcription:recording_missing"
    )
    assert len(run.report.partial_documents) == 1
    assert (
        next(value for value in run.report.transcriptions if value.filename == "second.png").status
        == "completed"
    )
    assert extraction.calls == 2


@pytest.mark.parametrize("failure", ["ocr", "key"])
def test_local_prerequisite_when_missing_keeps_text_and_makes_no_model_calls(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Real missing imports and absent selected credentials stay before HTTP and metering."""
    dataset = _mixed_dataset(db, tmp_path)
    profile = TranscriptionProfile(
        id="missing-prerequisite",
        backend="ocr" if failure == "ocr" else "vlm",
        mode="ocr" if failure == "ocr" else "vlm",
        model="fixture",
        base_url="https://vision.example/v1" if failure == "key" else None,
    )
    use_profile(monkeypatch, profile)
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    if failure == "key":

        @contextmanager
        def factory(*_args: object, **_kwargs: object) -> Iterator[VLMTranscriber]:
            with httpx.Client(
                transport=httpx.MockTransport(lambda _: pytest.fail("HTTP"))
            ) as client:
                yield VLMTranscriber(profile, client, FakeTranscriber((transcript(), transcript())))

        monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
        monkeypatch.setattr(
            "datakeel.transcription.factory.get_settings", lambda: Settings(_env_file=None)
        )
    extraction = install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "partial"
    assert run.report.transcription_failed == 2
    reason = "ocr_not_installed" if failure == "ocr" else "api_key_missing"
    assert {item.reason for item in run.report.failures} == {f"transcription:{reason}"}
    assert extraction.calls == 1
    assert not [trace for trace in list_traces(db, run.id) if trace.call_type == "transcription"]


@pytest.mark.parametrize("bomb", [False, True])
def test_image_decode_when_invalid_or_decompression_bomb_continues_other_sources(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, bomb: bool
) -> None:
    """Real Pillow errors are preserved per source through preparation and authorized restore."""
    if bomb:
        Image.new("RGB", (400, 200), "white").save(tmp_path / "large.png")
    dataset = _mixed_dataset(db, tmp_path, malformed=not bomb)
    if bomb:
        dataset_row = import_paths(
            db,
            "Bomb mixed dataset",
            [tmp_path / "large.png", tmp_path / "second.png", tmp_path / "text.txt"],
        )
        version, files = source_manifest(db, dataset_row.id)
        dataset = TextDataset(dataset_id=dataset_row.id, version_id=version, files=tuple(files))
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 30000)
    use_profile(monkeypatch)
    extraction = install_adapter(monkeypatch, (pair_result(), pair_result()))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "partial"
    assert run.report.transcription_failed == 1
    assert run.report.failures[0].reason == "transcription:image_decode_error"
    assert extraction.calls == 2


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_original_image_api_when_transparent_returns_white_background(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The source drawer receives exactly the same white-backed pixels as transcription."""
    source = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    source.putpixel((2, 2), (0, 0, 0, 255))
    path = tmp_path / "transparent.png"
    source.convert(mode).save(path)
    imported = import_paths(db, "Transparent source", [path])
    version, files = source_manifest(db, imported.id)
    dataset = TextDataset(dataset_id=imported.id, version_id=version, files=tuple(files))
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "completed"
    relation = query_kg(db, KGQuery()).relations[0]
    explanation = explain_relation(db, relation.assertion.id)
    image_url = next(source.image_url for source in explanation.sources if source.image_url)
    with TestClient(create_app(db)) as client:
        response = client.get(image_url)
        assert response.status_code == 200
    with Image.open(BytesIO(response.content)) as corrected:
        assert corrected.getpixel((0, 0)) == (255, 255, 255)
        assert corrected.getpixel((2, 2)) == (0, 0, 0)
