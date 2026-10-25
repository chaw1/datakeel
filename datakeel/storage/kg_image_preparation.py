# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze image provenance and worst-case cost before invoking any transcription backend."""

import hashlib
from math import ceil
from pathlib import Path

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.errors import ValidationError
from datakeel.core.harness_pricing import nanos_to_usd, reservation_cost
from datakeel.core.kg_execution import KGDocument, KGPrepared
from datakeel.core.kg_images import KGImageSource, TranscriptionEstimate
from datakeel.core.kg_models import TextBlock
from datakeel.core.models import AssetRef, FileItem
from datakeel.core.transcription_models import TranscriptionMode, TranscriptionProfile
from datakeel.kg.prompt import extraction_prompt
from datakeel.storage.transcription_pricing import (
    transcription_external,
    transcription_host,
    transcription_metering,
)
from datakeel.transcription.cache import profile_digest
from datakeel.transcription.images import normalize_image
from datakeel.transcription.loader import read_recording
from datakeel.transcription.prompt import input_token_bound


def image_document(
    file: FileItem,
    profile: TranscriptionProfile,
    recording_hash: str | None = None,
    mode: TranscriptionMode | None = None,
) -> KGDocument:
    """Inspect corrected image dimensions and content without OCR or model requests."""
    selected_mode = mode or profile.mode
    if profile.backend == "ocr" and selected_mode != "ocr":
        msg = "The ocr backend supports only ocr mode"
        raise ValidationError(msg)
    image = normalize_image(Path(file.path).read_bytes())
    if file.sha256 and file.sha256 != image.image_hash:
        msg = "Graph image no longer matches its immutable manifest"
        raise ValidationError(msg)
    ref = AssetRef(
        asset_type="file", asset_id=file.id, version=image.image_hash, display_name=file.filename
    )
    return KGDocument(
        asset_ref=ref,
        filename=file.filename,
        text="",
        content_revision=image.image_hash,
        blocks=(),
        image=KGImageSource(
            asset_ref=ref,
            content_revision=image.image_hash,
            width=image.width,
            height=image.height,
            mode=selected_mode,
            profile_id=profile.id,
            profile_digest=profile_digest(profile, recording_hash, selected_mode),
            backend=profile.backend,
            model=profile.model,
        ),
    )


def prepare_images(
    prepared: KGPrepared, documents: tuple[KGDocument, ...], profile: TranscriptionProfile
) -> KGPrepared:
    """Add both outbound fingerprints and a conservative extraction-input upper bound."""
    images = tuple(document.image for document in documents if document.image is not None)
    remote_images = tuple(image for image in images if image.mode == "vlm")
    config = transcription_metering(profile, "prepare")
    image_tokens = sum(ceil(image.width * image.height / 1024 + 2) for image in images)
    transcription_cost = nanos_to_usd(
        reservation_cost(
            config.price,
            sum(input_token_bound(image.width, image.height) for image in remote_images),
            len(remote_images) * profile.max_output_tokens,
        )
    )
    estimate = prepared.estimate
    tokens, blocks = _extraction_bound(prepared, len(images), profile.max_output_tokens)
    cost = nanos_to_usd(
        reservation_cost(
            prepared.accounting_price,
            tokens,
            (estimate.blocks + blocks) * prepared.profile.max_output_tokens,
        )
    )
    recording_hash, _ = read_recording(profile)
    return prepared.model_copy(
        update={
            "transcription_profile": profile,
            "transcription_recording_hash": recording_hash,
            "transcription_accounting_price": config.price,
            "transcription_accounting_version": config.price_version,
            "external": prepared.external
            or (bool(remote_images) and transcription_external(profile)),
            "estimate": estimate.model_copy(
                update={
                    "extraction_input_basis": "transcription_limit",
                    "blocks": estimate.blocks + blocks,
                    "input_tokens": tokens,
                    "cost_upper_usd": cost if estimate.price else None,
                }
            ),
            "transcription_estimate": TranscriptionEstimate(
                target_host=transcription_host(profile) if remote_images else None,
                model=profile.model,
                images=len(images),
                image_tokens=image_tokens,
                max_output_tokens=profile.max_output_tokens,
                cost_upper_usd=transcription_cost
                if config.known_price or not remote_images
                else None,
                price=config.price if config.known_price else None,
                price_version=config.price_version if config.known_price else None,
            ),
        }
    )


def transcript_ref(source: KGImageSource, text: str) -> AssetRef:
    """Derive stable asset identity from the source and profile, with a text-content version."""
    identity = hashlib.sha256(
        f"{source.asset_ref.asset_id}:{source.profile_digest}".encode()
    ).hexdigest()
    return AssetRef(
        asset_type="image_transcript",
        asset_id=f"transcript-{identity}",
        version=hashlib.sha256(text.encode()).hexdigest(),
        display_name=source.asset_ref.display_name,
    )


def _extraction_bound(
    prepared: KGPrepared, image_count: int, max_output_tokens: int
) -> tuple[int, int]:
    overhead = estimate_tokens(
        extraction_prompt(
            TextBlock(text="", start=0, end=0),
            prepared.schema_definition,
            prepared.profile.prompt_version,
        )
    )
    # Every output token is conservatively budgeted as up to four UTF-8 bytes.
    output_bound = max_output_tokens * 4
    blocks = sum(
        ceil(output_bound / (prepared.profile.chunk_size - prepared.profile.chunk_overlap))
        for _ in range(image_count)
    )
    tokens = prepared.estimate.input_tokens + image_count * output_bound + blocks * overhead
    return tokens, blocks
