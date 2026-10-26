# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Malformed visual envelopes fail locally before any raw output reaches extraction."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.harness_models import TokenUsage
from datakeel.core.transcription_auto import OCRReference
from datakeel.core.transcription_models import (
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
)
from datakeel.kg.extractors import FakeExtractor
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_rows import KGRunRow
from datakeel.transcription.factory import create_transcriber
from tests.kg.integration_helpers import execute_graph, pair_result
from tests.worker.auto_helpers import FixtureSettings, ScriptedOCR
from tests.worker.image_helpers import image_dataset, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import ExtractionResult, TextBlock
    from datakeel.storage.database import Database
    from datakeel.transcription.quality import TranscriberAdapter


class _ObservedExtractor(FakeExtractor):
    def __init__(self) -> None:
        super().__init__((pair_result(), pair_result()))
        self.texts: list[str] = []

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        self.texts.append(block.text)
        return super().extract(block, schema)


def _observe_extraction(monkeypatch: pytest.MonkeyPatch) -> _ObservedExtractor:
    adapter = _ObservedExtractor()

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Generator[_ObservedExtractor]:
        yield adapter

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", factory)
    return adapter


def _mock_structured_visual(
    monkeypatch: pytest.MonkeyPatch, confidences: dict[str, float]
) -> list[httpx.Request]:
    ocr = ScriptedOCR(confidences)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"lines": invalid JSON}'}}],
                "usage": {"prompt_tokens": 37, "completion_tokens": 19},
            },
        )

    @contextmanager
    def factory(profile: TranscriptionProfile, **_kwargs: object) -> Generator[TranscriberAdapter]:
        with (
            httpx.Client(transport=httpx.MockTransport(respond)) as client,
            create_transcriber(profile, client=client, ocr=ocr) as adapter,
        ):
            yield adapter

    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", FixtureSettings.model_construct
    )
    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    return requests


def test_auto_unparseable_visual_output_fails_one_image_and_preserves_usage_and_ocr(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real worker settles a malformed response and extracts only the other OCR image."""
    dataset = image_dataset(db, tmp_path, 2)
    use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="structured-fixture",
            backend="vlm",
            mode="auto",
            model="gpt-4.1-mini",
            base_url="https://vision.example/v1",
            prompt_version="image-transcription-v2",
        ),
    )
    requests = _mock_structured_visual(
        monkeypatch, {dataset.files[0].sha256: 0.2, dataset.files[1].sha256: 0.99}
    )
    extractor = _observe_extraction(monkeypatch)
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "partial"
    assert run.report.transcription_failed == 1
    assert run.report.failures[0].reason == "transcription:unparseable_structured_output"
    failed, successful = run.report.transcriptions
    assert failed.status == "failed"
    assert failed.mode == "vlm"
    assert failed.external
    assert "unparseable_structured_output" in failed.quality_issues
    assert failed.ocr_reference == OCRReference(text="Acme uses Widget.")
    assert "low_confidence" in failed.reasons
    assert successful.status == "completed"
    assert successful.mode == "ocr"
    assert len(requests) == 1
    assert run.report.transcription_external_images == 1
    assert extractor.texts == ["Acme uses Widget."]
    traces = [trace for trace in list_traces(db, run.id) if trace.call_type == "transcription"]
    assert len(traces) == 1
    assert traces[0].usage == TokenUsage(input_tokens=37, output_tokens=19)
    assert traces[0].billing_status == "actual"
    with db.session() as session:
        row = session.get(KGRunRow, run.id)
        assert row is not None
        assert "invalid JSON" not in str(row.payload)


def test_replay_unparseable_raw_output_fails_one_image_and_keeps_other_transcript(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit wire recordings use the same local failure path as HTTP structured output."""
    dataset = image_dataset(db, tmp_path, 2)
    records = tuple(
        TranscriptionRecord(
            **transcript().model_copy(update={"backend": "vlm", "mode": "vlm"}).model_dump(),
            image_hash=file.sha256,
            raw_output=(
                '{"unexpected":"wire response"}'
                if index == 0
                else '{"lines":[{"text":"Acme uses Widget.","bbox":[10,20,180,40],"color":"gray"}]}'
            ),
        )
        for index, file in enumerate(dataset.files)
    )
    archive = TranscriptionRecording(
        model="recorded-fixture",
        recorded_at="2026-10-27",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=records,
    )
    path = tmp_path / "structured-recording.json"
    path.write_text(archive.model_dump_json())
    use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="structured-replay",
            backend="replay",
            mode="vlm",
            model="recorded-fixture",
            recording=str(path),
        ),
    )
    extractor = _observe_extraction(monkeypatch)
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "partial"
    assert run.report.transcription_failed == 1
    assert run.report.failures[0].reason == "transcription:unparseable_structured_output"
    assert [item.status for item in run.report.transcriptions] == ["failed", "completed"]
    assert run.report.transcriptions[1].ignored_field_count == 1
    assert extractor.texts == ["Acme uses Widget."]
    assert not [trace for trace in list_traces(db, run.id) if trace.call_type == "transcription"]
