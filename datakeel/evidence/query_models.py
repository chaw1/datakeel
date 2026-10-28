# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public evidence queries, presentation models, and auditable sample explanations."""

from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.evidence_models import (
    Assertion,
    AssertionStatus,
    PredicateId,
    Presence,
    TextSpan,
)
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.ontology.models import ObjectKind, ObjectSet, PropertyFilter


class EvidenceQuery(ObjectSet):
    """Paginate an evidence ObjectSet by the final asset identity of the previous page."""

    # Keep the inherited field type invariant while publishing the validated file-only schema.
    object_type: ObjectKind = Field(default="file", json_schema_extra={"enum": ["file"]})
    # One of the base ObjectSet's 32 filters is reserved for paired-image identity.
    filters: list[PropertyFilter] = Field(default_factory=list[PropertyFilter], max_length=31)
    cursor: str | None = Field(default=None, min_length=1)
    page_size: int = Field(default=50, ge=1, le=200)
    sort: Literal["asset", "review", "filename", "quality"] = "asset"

    @model_validator(mode="after")
    def validate_file_query(self) -> Self:
        """Keep this view limited to original file sample objects."""
        if self.object_type != "file":
            msg = "Evidence queries require file objects"
            raise ValueError(msg)
        return self

    def selection(self) -> ObjectSet:
        """Remove presentation pagination before freezing the underlying object selection."""
        selection = ObjectSet.model_validate(
            self.model_dump(exclude={"cursor", "page_size", "sort"})
        )
        paired = PropertyFilter(
            field="metadata.evidence_sample.sample_key", operator="ne", value=None
        )
        return selection.model_copy(update={"filters": [*selection.filters, paired]})


class EvidenceBox(BoundaryModel):
    """Describe a canonical annotation in original-image pixel xyxy coordinates."""

    concept: str
    bbox: tuple[float, float, float, float]
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class NearDuplicateCandidate(BoundaryModel):
    """Explain one directly measured neighboring sample, without transitive expansion."""

    asset_ref: AssetRef
    distance: int = Field(ge=0)
    reason: str
    assertion_id: str


class EvidenceSample(BoundaryModel):
    """Expose evidence and source provenance without private materialized file paths."""

    asset_ref: AssetRef
    dataset_id: str
    source_version: str
    filename: str
    split: Literal["train", "val", "test"] | None
    thumbnail_url: str | None
    caption: str | None
    caption_spans: list[TextSpan]
    annotation_boxes: list[EvidenceBox]
    assertions: list[Assertion]
    quality_score: float = Field(ge=0, le=100)
    near_duplicates: list[NearDuplicateCandidate]
    quarantined: bool
    deleted: bool
    image_width: int | None = None
    image_height: int | None = None


class EvidenceQueryResult(BoundaryModel):
    """Return deterministic, bounded sample pages and their full selected denominator."""

    items: list[EvidenceSample]
    next_cursor: str | None
    total: int = Field(ge=0)
    truncated: bool = False


class EvidenceState(BoundaryModel):
    """Keep a readable state tied to the exact assertion and review status."""

    predicate: PredicateId
    concept: str | None
    value: Presence
    status: AssertionStatus
    reason: str | None


class EvidenceExplanation(BoundaryModel):
    """Present all observed states and complete evidence for independent inspection."""

    asset_ref: AssetRef
    text: str
    assertions: list[Assertion]
    states: list[EvidenceState]
