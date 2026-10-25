# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cancellation during local OCR must fence the later visual provider attempt."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import func, select

from datakeel.core.settings import Settings
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_store import list_runs
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.transcription.factory import VLMTranscriber
from datakeel.worker.queue import DatabaseQueue
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import image_dataset, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
        TranscriptionResult,
    )
    from datakeel.storage.database import Database


CANCELLATION_PROFILE = TranscriptionProfile(
    id="cancel-during-ocr",
    backend="vlm",
    mode="vlm",
    model="fixture-vision",
    base_url="http://127.0.0.1:8000/v1",
)


def test_cancel_during_local_ocr_prevents_visual_request_and_budget_reservation(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh lease check is required after slow OCR and before a new model request."""
    dataset = image_dataset(db, tmp_path)
    profile = use_profile(monkeypatch, CANCELLATION_PROFILE)
    requests: list[httpx.Request] = []
    ocr_calls: list[str] = []

    class CancellingOCR:
        def transcribe(
            self, image: ImageInput, mode: TranscriptionMode | None = None
        ) -> TranscriptionResult:
            """Cancel the real active task before returning locally computed OCR lines."""
            ocr_calls.append(image.image_hash)
            task_id = list_runs(db)[0].task_id
            assert task_id is not None
            assert DatabaseQueue(db).cancel(task_id)
            return transcript().model_copy(update={"backend": "ocr", "model": "fixture-ocr"})

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Acme uses Widget."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Generator[VLMTranscriber]:
        with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client:
            yield VLMTranscriber(profile, client, CancellingOCR())

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", Settings.model_construct)
    extraction = install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    assert len(ocr_calls) == 1
    assert run.status == "failed"
    with db.session() as session:
        observed = {
            "model_requests": len(requests),
            "traces": len(list_traces(db, run.id)),
            "reservations": session.scalar(select(func.count()).select_from(BudgetReservationRow)),
            "cached_transcriptions": session.scalar(
                select(func.count()).select_from(TranscriptionRow)
            ),
            "extraction_calls": extraction.calls,
        }
    assert observed == dict.fromkeys(observed, 0)
