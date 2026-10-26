# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Construct typed transcribers while keeping offline paths free from credential reads."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import TYPE_CHECKING

import httpx

from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.transcription.adapters import FakeTranscriber, ReplayTranscriber
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.loader import read_recording
from datakeel.transcription.ocr import RapidOCRTranscriber
from datakeel.transcription.policy import is_external
from datakeel.transcription.transport import request_transcription

if TYPE_CHECKING:
    from collections.abc import Generator

    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
        TranscriptionProfile,
        TranscriptionRecording,
        TranscriptionResult,
    )
    from datakeel.transcription.quality import TranscriberAdapter


class VLMTranscriber:
    """Always obtain OCR line geometry before optional visual structure transcription."""

    def __init__(
        self, profile: TranscriptionProfile, client: httpx.Client, ocr: TranscriberAdapter
    ) -> None:
        """Retain explicit transport and OCR adapters without reading secrets."""
        self.profile, self.client, self.ocr = profile, client, ocr
        self.prepared_hash: str | None = None
        self.prepared_mode: TranscriptionMode | None = None
        self.prepared_result: TranscriptionResult | None = None
        self.credentials = ""
        self.seeded_hash: str | None = None

    def prepare(self, image: ImageInput, mode: TranscriptionMode | None = None) -> None:
        """Complete local OCR and credential validation before any provider budget reservation."""
        selected = mode or self.profile.mode
        if (self.prepared_hash, self.prepared_mode) == (image.image_hash, selected):
            return
        result = (
            self.prepared_result
            if self.seeded_hash == image.image_hash and self.prepared_result is not None
            else self.ocr.transcribe(image, "ocr")
        )
        self.seeded_hash = None
        credentials = ""
        if selected == "vlm":
            key = get_settings().extraction_key(self.profile.api_key_env)
            if key is None and is_external(self.profile):
                message = "No transcription API key configured for the selected external provider"
                raise TranscriptionUnavailableError(message, reason="api_key_missing")
            credentials = key.get_secret_value() if key else ""
        self.prepared_hash, self.prepared_mode = image.image_hash, selected
        self.prepared_result, self.credentials = result, credentials

    def seed_ocr(self, image: ImageInput, result: TranscriptionResult) -> None:
        """Reuse the exact local attempt when auto falls back after an OCR failure."""
        self.prepared_hash, self.prepared_mode = image.image_hash, "ocr"
        self.prepared_result, self.credentials = result, ""
        self.seeded_hash = image.image_hash

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Read only the selected credential after OCR and explicit OCR-only routing."""
        self.prepare(image, mode)
        result = self.prepared_result
        if result is None:
            message = "Transcription preparation did not produce OCR geometry"
            raise ValidationError(message)
        if (mode or self.profile.mode) == "ocr":
            return result
        return request_transcription(self.profile, image, result, self.client, self.credentials)


def prepare_transcriber(
    adapter: TranscriberAdapter, image: ImageInput, mode: TranscriptionMode | None = None
) -> None:
    """Allow a metering wrapper to reject preflight failures before counting a remote attempt."""
    if isinstance(adapter, AutoTranscriber):
        route = adapter.resolve(image).route if mode in {None, "auto"} else mode
        prepare_transcriber(adapter.adapter, image, route)
    elif isinstance(adapter, VLMTranscriber):
        adapter.prepare(image, mode)


@contextmanager
def create_transcriber(
    profile: TranscriptionProfile,
    *,
    recording: TranscriptionRecording | None = None,
    client: httpx.Client | None = None,
    ocr: TranscriberAdapter | None = None,
) -> Generator[TranscriberAdapter]:
    """Own only factory-created clients and never construct them for offline backends."""
    if profile.backend in {"replay", "fake"}:
        archive = recording or read_recording(profile)[1]
        if archive is not None:
            replay = ReplayTranscriber(archive, profile.mode, profile.ocr_model_version)
            yield (
                AutoTranscriber(replay, profile.auto_routing) if profile.mode == "auto" else replay
            )
        elif profile.backend == "fake":
            fake = FakeTranscriber()
            yield AutoTranscriber(fake, profile.auto_routing) if profile.mode == "auto" else fake
        else:
            message = "Replay transcription requires a recording"
            raise ValidationError(message)
        return
    engine = ocr or RapidOCRTranscriber(profile.ocr_model_version)
    if profile.backend == "ocr":
        yield engine
        return
    owned = (
        httpx.Client(trust_env=False, follow_redirects=False)
        if client is None
        else nullcontext(client)
    )
    with owned as transport:
        visual = VLMTranscriber(profile, transport, engine)
        yield (
            AutoTranscriber(visual, profile.auto_routing, visual.seed_ocr)
            if profile.mode == "auto"
            else visual
        )
