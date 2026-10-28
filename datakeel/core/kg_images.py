# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image provenance, consent estimates and durable transcription observations."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from datakeel.core.evidence_models import ContentRevision
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.transcription_auto import AutoReason, OCRReference
from datakeel.core.transcription_models import (
    ImageInput,
    OCRLine,
    TranscriptionIssue,
    TranscriptionMode,
)


class KGImageSource(BoundaryModel):
    """Bind corrected image coordinates and transcription identity to the original content."""

    asset_ref: AssetRef
    content_revision: ContentRevision
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    decode_error: Literal["image_decode_error"] | None = None
    mode: TranscriptionMode
    profile_id: str = ""
    profile_digest: str = ""
    backend: str = ""
    model: str = ""
    lines: tuple[OCRLine, ...] = ()


class KGImageInput(BoundaryModel):
    """Carry decoded pixels only within the authorized execution boundary."""

    file_id: str
    image: ImageInput


class KGTranscriptionSource(BoundaryModel):
    """Freeze the actual per-image route beside its immutable transcript asset."""

    asset_ref: AssetRef
    backend: str
    model: str
    profile_id: str
    mode: TranscriptionMode


class ImageTransfer(BoundaryModel):
    """Bind every potentially outbound image to the consent envelope."""

    file_id: str
    filename: str
    image_hash: ContentRevision
    mode: TranscriptionMode


class TranscriptionEstimate(BoundaryModel):
    """Show the image transfer envelope independently from downstream extraction."""

    target_host: str | None
    model: str
    images: int = Field(ge=0)
    image_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(gt=0)
    cost_upper_usd: Decimal | None = None
    price: ModelPrice | None = None
    price_version: str | None = None
    possible_external_images: tuple[ImageTransfer, ...] = ()
    auto_images: int = Field(default=0, ge=0)


class TranscriptionObservation(BoundaryModel):
    """Expose one selected route, cache outcome and explicit quality failure per image."""

    file_id: str
    filename: str
    backend: str
    mode: TranscriptionMode
    model: str
    cached: bool = False
    status: Literal["completed", "failed", "unexecuted"] = "completed"
    error: str | None = None
    reasons: tuple[AutoReason, ...] = ()
    external: bool = False
    ocr_reference: OCRReference | None = None
    quality_issues: tuple[TranscriptionIssue, ...] = ()
    ignored_field_count: int = Field(default=0, ge=0)
