# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transcription preflight and lease failures cannot create model charges or cached output."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.kg_execution import KGLeaseFence
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.harness_service import list_traces
from datakeel.storage.transcription_store import cached_transcription, save_transcription
from datakeel.transcription.factory import VLMTranscriber
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import image_dataset, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
        TranscriptionResult,
    )
    from datakeel.storage.database import Database


class MissingOCR:
    """Represent an unavailable optional engine before any visual request can start."""

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Fail locally without credential access or model transport."""
        message = "Optional OCR engine is unavailable"
        raise ImportError(message)


def test_ocr_preflight_failure_has_no_model_trace_or_extraction(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metering starts only after local prerequisites, and the failed image remains visible."""
    dataset = image_dataset(db, tmp_path)
    profile = use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="preflight",
            backend="vlm",
            mode="vlm",
            model="fixture",
            base_url="http://127.0.0.1:8000/v1",
        ),
    )

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Iterator[VLMTranscriber]:
        with httpx.Client(
            transport=httpx.MockTransport(lambda _: pytest.fail("Model request"))
        ) as client:
            yield VLMTranscriber(profile, client, MissingOCR())

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", lambda: pytest.fail("Credential read")
    )
    extraction = install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.report.transcriptions[0].error == "ocr_not_installed"
    assert run.report.transcription_failed == 1
    assert run.report.cloud_calls == 0
    assert not list_traces(db, run.id)
    assert extraction.calls == 0


def test_transcription_cache_rejects_failed_or_unowned_publication(db: Database) -> None:
    """Neither failed quality nor a stale worker fence can populate reusable transcripts."""
    fence = KGLeaseFence(task_id="absent", shard_id="absent", owner="old-owner")
    assert not save_transcription(db, fence, "never-published", transcript())
    assert cached_transcription(db, "never-published") is None
    with pytest.raises(ValidationError, match="Failed transcription"):
        save_transcription(db, fence, "failed", transcript().model_copy(update={"text": ""}))
    assert cached_transcription(db, "failed") is None
