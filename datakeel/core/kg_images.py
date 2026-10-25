# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image provenance, consent estimates and durable transcription observations."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from datakeel.core.evidence_models import ContentRevision
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.transcription_models import ImageInput, OCRLine


class KGImageSource(BoundaryModel):
    """Bind corrected image coordinates and transcription identity to the original content."""

    asset_ref: AssetRef
    content_revision: ContentRevision
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mode: Literal["ocr", "vlm"]
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
    mode: Literal["ocr", "vlm"]


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


class TranscriptionObservation(BoundaryModel):
    """Expose one selected route, cache outcome and explicit quality failure per image."""

    file_id: str
    filename: str
    backend: str
    mode: Literal["ocr", "vlm"]
    model: str
    cached: bool = False
    status: Literal["completed", "failed", "unexecuted"] = "completed"
    error: str | None = None
