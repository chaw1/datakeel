# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist and explain per-source model attribution for mixed image transcription routes."""

from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_execution import KGJob
from datakeel.core.kg_images import KGTranscriptionSource
from datakeel.core.models import AssetRef, LineageEvent


def _key(ref: AssetRef) -> tuple[str, str, str]:
    return ref.asset_type, ref.asset_id, ref.version or ""


def transcription_sources(job: KGJob) -> tuple[KGTranscriptionSource, ...]:
    """Capture actual OCR overrides instead of presenting a run-wide visual model."""
    return tuple(
        KGTranscriptionSource(
            asset_ref=document.asset_ref,
            backend=document.image.backend,
            model=document.image.model,
            profile_id=document.image.profile_id,
            mode=document.image.mode,
        )
        for document in job.documents
        if document.image is not None
    )


def relation_transcriptions(
    assertion: Assertion, events: tuple[LineageEvent, ...]
) -> tuple[KGTranscriptionSource, ...]:
    """Resolve each exact transcript anchor, including sources retained from earlier runs."""
    references = {_key(anchor.asset_ref) for anchor in assertion.anchors}
    sources = {
        _key(source.asset_ref): source
        for event in events
        for value in event.params.get("kg_transcription_sources", [])
        if _key((source := KGTranscriptionSource.model_validate(value)).asset_ref) in references
    }
    return tuple(sources[key] for key in sorted(sources))
