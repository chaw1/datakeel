# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Construct and scope injected graph extractors at the application boundary."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager, nullcontext
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import httpx

from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor
from datakeel.kg.gliner import GlinerExtractor
from datakeel.kg.loader import contracts_path
from datakeel.kg.policy import is_external

if TYPE_CHECKING:
    from collections.abc import Generator

    from datakeel.core.kg_contracts import ExtractionProfile
    from datakeel.core.kg_models import Recording
    from datakeel.kg.extractors import ExtractorAdapter


class _LLMModule(Protocol):
    def llm_extractor(
        self, profile: ExtractionProfile, api_key: str, client: httpx.Client, timeout: float
    ) -> AbstractContextManager[ExtractorAdapter]: ...


def _offline(profile: ExtractionProfile, recording: Recording | None) -> ExtractorAdapter:
    if profile.extractor in {"fake", "replay"} and recording is not None:
        return ReplayExtractor(recording)
    if profile.extractor == "fake" and not profile.recording:
        return FakeExtractor()
    if profile.extractor in {"fake", "replay"} and profile.recording:
        path = Path(profile.recording)
        return ReplayExtractor.from_path(path if path.is_absolute() else contracts_path() / path)
    if profile.extractor == "gliner2":
        return GlinerExtractor(profile.model)
    message = "The selected extraction adapter is not available"
    raise ValidationError(message)


@contextmanager
def create_extractor(
    profile: ExtractionProfile,
    *,
    client: httpx.Client | None = None,
    recording: Recording | None = None,
) -> Generator[ExtractorAdapter]:
    """Avoid credential reads offline and own only HTTP clients created by this factory."""
    if profile.extractor != "llm":
        yield _offline(profile, recording)
        return
    module = cast("_LLMModule", import_module("datakeel.extraction_runtime.adapter"))
    settings = get_settings()
    key = settings.extraction_key(profile.api_key_env)
    if key is None and is_external(profile):
        message = "No extraction API key configured for the selected external provider"
        raise ValidationError(message)
    credentials = key.get_secret_value() if key else "not-required"
    owned = (
        httpx.Client(trust_env=False, follow_redirects=False)
        if client is None
        else nullcontext(client)
    )
    with (
        owned as transport,
        module.llm_extractor(profile, credentials, transport, settings.provider_timeout) as adapter,
    ):
        yield adapter
