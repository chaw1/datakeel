# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed graph products prepared for existing evidence publication."""

from typing import Literal

from pydantic import Field

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import ContentRevision, ExtractorRef
from datakeel.core.kg_contracts import ExtractedRelation
from datakeel.core.models import AssetRef, BoundaryModel


class KGSource(BoundaryModel):
    """Bind normalized document content to immutable dataset and file provenance."""

    dataset_id: str
    dataset_version_id: str
    file: AssetRef
    text: str
    content_revision: ContentRevision
    extractor: ExtractorRef
    block_start: int = Field(default=0, ge=0)
    block_end: int | None = Field(default=None, ge=0)


class KGEntity(BoundaryModel):
    """Expose the deterministic entity identity alongside its readable spelling."""

    asset_ref: AssetRef
    name: str
    type: str


class SchemaProposal(BoundaryModel):
    """Count excluded claims without silently extending the active vocabulary."""

    reason: Literal["unknown_relation", "domain_range", "endpoint_ambiguous", "unknown_entity_type"]
    count: int = Field(ge=1)
    samples: tuple[ExtractedRelation, ...] = Field(max_length=20)


class ProductExtraction(BoundaryModel):
    """Keep entities, evidence drafts and exclusions together through publication."""

    entities: tuple[KGEntity, ...] = ()
    drafts: tuple[ObservationDraft, ...] = ()
    proposals: tuple[SchemaProposal, ...] = ()
