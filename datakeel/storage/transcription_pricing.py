# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reuse frozen provider tariffs for image transfer without constructing a transport."""

from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_execution import KGMeteringConfig
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.kg.policy import is_external, target_host
from datakeel.storage.kg_pricing import metering_config


def billing_profile(profile: TranscriptionProfile) -> ExtractionProfile:
    """Project only model identity and endpoint for shared pricing and literal-host policy."""
    remote = profile.backend == "vlm"
    return ExtractionProfile(
        id=profile.id,
        extractor="llm" if remote else "fake",
        provider="openai" if remote else "fake",
        model=profile.model,
        base_url=profile.base_url,
        max_output_tokens=profile.max_output_tokens,
    )


def transcription_metering(profile: TranscriptionProfile, run_id: str) -> KGMeteringConfig:
    """Use the same conservative unknown-price budget envelope as text extraction."""
    return metering_config(billing_profile(profile), run_id)


def transcription_external(profile: TranscriptionProfile) -> bool:
    """Classify the independent transcription endpoint without any network lookup."""
    return is_external(billing_profile(profile))


def transcription_host(profile: TranscriptionProfile) -> str | None:
    """Expose the literal destination used by the frozen transcription profile."""
    return target_host(billing_profile(profile))
