# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed extractor observations before an authoritative run binds event provenance."""

from pydantic import Field

from datakeel.core.evidence_models import (
    EvidenceAnchor,
    EvidenceValue,
    ExtractorRef,
    PredicateId,
    Verification,
    VerificationDetail,
)
from datakeel.core.models import AssetRef, BoundaryModel


class ObservationDraft(BoundaryModel):
    """Carry observed facts without minting persisted assertion or event identities."""

    subject: AssetRef
    predicate: PredicateId
    object: AssetRef | EvidenceValue
    anchors: tuple[EvidenceAnchor, ...] = Field(min_length=1)
    extractor: ExtractorRef
    confidence: float | None = Field(default=None, ge=0, le=1)
    distance: int | None = Field(default=None, ge=0)
    reason: str | None = None
    verification: Verification | None = Field(default=None, exclude_if=lambda value: value is None)
    verification_detail: VerificationDetail | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
