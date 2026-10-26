# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline local-OCR and mock-HTTP fixtures for the automatic worker path."""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from pydantic import SecretStr

from datakeel.core.settings import Settings
from datakeel.core.transcription_models import (
    ImageInput,
    TranscriptionMode,
    TranscriptionProfile,
    TranscriptionResult,
)
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.quality import TranscriberAdapter
from tests.worker.image_helpers import transcript, use_profile


class ScriptedOCR:
    """Select confidence by immutable fixture content, without making model requests."""

    def __init__(self, confidences: dict[str, float]) -> None:
        """Retain fixture signals and count actual local attempts."""
        self.confidences, self.calls = confidences, 0

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Return typed OCR with the requested fixture confidence."""
        self.calls += 1
        result = transcript()
        lines = tuple(
            line.model_copy(update={"confidence": self.confidences[image.image_hash]})
            for line in result.lines
        )
        return result.model_copy(update={"backend": "ocr", "mode": "ocr", "lines": lines})


class FixtureSettings(Settings):
    """Avoid reading any environment credentials when exercising mock HTTP transport."""

    def extraction_key(self, environment_name: str | None) -> SecretStr:
        """Return only an explicit fixture value; there is no real provider connection."""
        return SecretStr("fixture")


def visual_profile(monkeypatch: pytest.MonkeyPatch) -> TranscriptionProfile:
    """Select a known-price external identity while replacing its entire transport."""
    return use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="automatic-fixture",
            backend="vlm",
            mode="auto",
            model="gpt-4.1-mini",
            base_url="https://vision.example/v1",
        ),
    )


def install_visual(
    monkeypatch: pytest.MonkeyPatch, confidences: dict[str, float]
) -> tuple[ScriptedOCR, list[httpx.Request]]:
    """Exercise production routing, metering and transport using a local HTTP mock."""
    ocr, requests = ScriptedOCR(confidences), []

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
    def factory(profile: TranscriptionProfile, **_kwargs: object) -> Iterator[TranscriberAdapter]:
        with (
            httpx.Client(transport=httpx.MockTransport(respond)) as client,
            create_transcriber(profile, client=client, ocr=ocr) as adapter,
        ):
            yield adapter

    monkeypatch.setattr(
        "datakeel.transcription.factory.get_settings", FixtureSettings.model_construct
    )
    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    return ocr, requests
