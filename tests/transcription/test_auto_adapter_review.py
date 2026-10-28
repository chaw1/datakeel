# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check failed local OCR and independent images through real offline auto adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Never

import httpx
import numpy as np
import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.ocr import RapidOCRTranscriber
from datakeel.transcription.quality import checked_transcribe
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.auto_helpers import FixtureSettings, install_visual, visual_profile
from tests.worker.image_helpers import image_dataset, prepare_image

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
    )
    from datakeel.storage.database import Database


class FailingOCR:
    """Represent optional engine failures without loading OCR packages or model clients."""

    def __init__(self, failure: str) -> None:
        """Keep the requested exception category and observed local attempt count."""
        self.failure, self.calls = failure, 0

    def transcribe(self, image: ImageInput, mode: TranscriptionMode | None = None) -> Never:
        """Raise the same exception classes possible at the optional OCR invocation boundary."""
        self.calls += 1
        message = "Generated OCR engine failure"
        if self.failure == "unavailable":
            raise TranscriptionUnavailableError(message, reason="ocr_not_installed")
        if self.failure == "timeout":
            raise TimeoutError(message)
        raise AssertionError(message)


@dataclass(frozen=True)
class EngineOutput:
    """Expose only the pinned OCR interface's normal output fields."""

    boxes: NDArray[np.float32]
    txts: tuple[str, ...]
    scores: tuple[float, ...]


class ScriptedEngine:
    """Fail once at a real OCR adapter boundary, then provide a normal local result."""

    def __init__(self, failure: str) -> None:
        """Select invocation or malformed-output failure without importing optional packages."""
        self.failure, self.calls = failure, 0

    def __call__(self, pixels: NDArray[np.uint8]) -> EngineOutput:
        """Produce either a native exception, mismatched tuple lengths, or valid geometry."""
        self.calls += 1
        if self.failure == "runtime" and self.calls == 1:
            message = "Generated native OCR runtime failure"
            raise RuntimeError(message)
        return EngineOutput(
            boxes=np.asarray([[(10, 20), (110, 20), (110, 40), (10, 40)]], dtype=np.float32),
            txts=("Acme uses Widget.", "Mismatched extra line")
            if self.failure == "value" and self.calls == 1
            else ("Acme uses Widget.",),
            scores=(0.99,),
        )


@pytest.mark.parametrize("failure", ["unavailable", "timeout", "runtime", "value"])
def test_auto_ocr_exception_can_still_use_approved_visual_fallback(
    image_input: ImageInput, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """A local engine failure should produce an explained visual result after one OCR attempt."""
    profile = visual_profile(monkeypatch)
    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", FixtureSettings.model_construct
    )
    requests: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Acme uses Widget."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    engine = ScriptedEngine(failure)
    native = RapidOCRTranscriber()
    native.engine = engine
    ocr = FailingOCR(failure) if failure in {"unavailable", "timeout"} else native
    with (
        httpx.Client(transport=httpx.MockTransport(response)) as client,
        create_transcriber(profile, client=client, ocr=ocr) as adapter,
    ):
        result = checked_transcribe(adapter, image_input, "auto")
    assert result.mode == "vlm"
    assert result.auto_decision is not None
    assert result.auto_decision.reasons == ("ocr_failed",)
    assert result.ocr_reference is not None
    assert result.ocr_reference.error
    assert result.text == "Acme uses Widget."
    assert (ocr.calls if isinstance(ocr, FailingOCR) else engine.calls) == len(requests) == 1


def test_auto_runtime_ocr_failure_does_not_abort_remaining_images(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OCR engine failure must not prevent the next image from completing locally."""
    dataset = image_dataset(db, tmp_path, 2)
    visual_profile(monkeypatch)
    ocr, requests = install_visual(monkeypatch, {file.sha256: 0.99 for file in dataset.files})
    native = RapidOCRTranscriber()
    engine = ScriptedEngine("runtime")
    native.engine = engine
    monkeypatch.setattr(ocr, "transcribe", native.transcribe)
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == "completed"
    assert [item.mode for item in run.report.transcriptions] == ["vlm", "ocr"]
    assert len(requests) == 1
    assert engine.calls == 2
