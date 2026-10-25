# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Behavioral image guards remain observable under isolated mutation tests."""

import hashlib

from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_images import KGImageSource
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGSource
from datakeel.core.models import AssetRef
from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import (
    ImageInput,
    TranscriptionMode,
    TranscriptionProfile,
    TranscriptionResult,
)
from datakeel.evidence.kg_images import enrich_image_product
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.loader import get_schema
from datakeel.kg.text import chunk_text
from datakeel.transcription.cache import cache_key
from datakeel.transcription.quality import checked_transcribe


def test_image_without_ocr_regions_stays_a_review_candidate() -> None:
    """Exact transcript evidence cannot make missing pixel evidence appear located."""
    text = "Cedar Unit uses AtlasBoard."
    revision = hashlib.sha256(text.encode()).hexdigest()
    transcript = AssetRef(asset_type="image_transcript", asset_id="transcript", version=revision)
    document = KGDocument(
        asset_ref=transcript,
        filename="diagram.png transcript",
        text=text,
        content_revision=revision,
        blocks=chunk_text(text, 4000, 200),
        image=KGImageSource(
            asset_ref=AssetRef(asset_type="file", asset_id="image", version="version"),
            content_revision="a" * 64,
            width=200,
            height=100,
            mode="vlm",
            lines=(),
        ),
    )
    raw = RawExtraction(
        entities=(
            ExtractedEntity(name="Cedar Unit", type="organization"),
            ExtractedEntity(name="AtlasBoard", type="system"),
        ),
        relations=(
            ExtractedRelation(head="Cedar Unit", relation="uses", tail="AtlasBoard", evidence=text),
        ),
    )
    schema = get_schema()
    product = assemble_extraction(
        raw,
        schema,
        KGSource(
            dataset_id="fixture",
            dataset_version_id="version",
            file=transcript,
            text=text,
            content_revision=revision,
            extractor=ExtractorRef(id="fake", version="1"),
        ),
    )
    enriched = enrich_image_product(product, document, schema)
    relation = next(item for item in enriched.drafts if item.predicate == "kg.uses")
    assert relation.verification == "needs_review"
    assert relation.verification_detail is not None
    assert "image_unlocated" in {issue.code for issue in relation.verification_detail.issues}
    assert not any(
        anchor.selector and anchor.selector.type == "image_region" for anchor in relation.anchors
    )


class _Truncated:
    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        del mode
        return TranscriptionResult(
            text="Readable but incomplete",
            width=image.width,
            height=image.height,
            backend="fake",
            finish_reason="length",
        )


def test_transcription_truncation_cannot_silently_pass() -> None:
    """Require a typed quality failure rather than accepting a superficially readable prefix."""
    reason = None
    try:
        checked_transcribe(
            _Truncated(), ImageInput(image_hash="a" * 64, png=b"fixture", width=2, height=2)
        )
    except TranscriptionFailure as error:
        reason = error.reason
    assert reason == "truncated"


def test_transcription_model_participates_in_cache_identity() -> None:
    """A new visual model must never reuse an earlier model's transcript for identical pixels."""
    profile = TranscriptionProfile(id="fixture", backend="fake", model="first")
    first = cache_key("a" * 64, profile)
    second = cache_key("a" * 64, profile.model_copy(update={"model": "second"}))
    assert first != second
