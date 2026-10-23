# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned evidence boundaries shared by extractors and transactional storage."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from datakeel.core.models import AssetRef, BoundaryModel, new_id, utcnow
from datakeel.core.predicate_registry import Predicate, PredicateId, predicate

Presence = Literal["present", "absent", "unknown"]
AssertionStatus = Literal["candidate", "accepted", "rejected"]
ContentRevision = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Whole(BoundaryModel):
    """Locate the entire revision of an asset."""

    type: Literal["whole"] = "whole"


class TextSpan(BoundaryModel):
    """Locate a half-open Unicode code-point interval after NFC normalization."""

    type: Literal["text_span"] = "text_span"
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        """Require a nonempty forward interval."""
        if self.start >= self.end:
            msg = "Text span end must exceed start"
            raise ValueError(msg)
        return self


class ImageRegion(BoundaryModel):
    """Locate an xyxy box in the original image pixel coordinate system."""

    type: Literal["image_region"] = "image_region"
    bbox: tuple[float, float, float, float]
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_box(self) -> Self:
        """Reject empty boxes or coordinates outside the declared dimensions."""
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height):
            msg = "Image region must lie within the image"
            raise ValueError(msg)
        return self


Selector = Annotated[Whole | TextSpan | ImageRegion, Field(discriminator="type")]


def require_version(ref: AssetRef) -> None:
    """Require evidence references to identify an immutable source version."""
    if not ref.version:
        msg = "Evidence asset references require a version"
        raise ValueError(msg)


class EvidenceAnchor(BoundaryModel):
    """Bind a modality-specific location to exact immutable content."""

    schema_version: Literal["1.0"] = "1.0"
    asset_ref: AssetRef
    content_revision: ContentRevision
    selector: Selector = Field(default_factory=Whole)

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        """Keep evidence independent of mutable paths and latest-version aliases."""
        require_version(self.asset_ref)
        return self


class ExtractorRef(BoundaryModel):
    """Identify the implementation and version responsible for an observation."""

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EvidenceValue(BoundaryModel):
    """Represent presence, measured absence, or missing evidence for a concept."""

    concept: str | None = None
    value: Presence


class Assertion(BoundaryModel):
    """Keep extraction content immutable while exposing a decision overlay."""

    id: str = Field(default_factory=new_id)
    subject: AssetRef
    predicate: PredicateId
    object: AssetRef | EvidenceValue
    status: AssertionStatus = "candidate"
    confidence: float | None = Field(default=None, ge=0, le=1)
    anchors: tuple[EvidenceAnchor, ...] = Field(min_length=1)
    extractor: ExtractorRef
    schema_version: Literal["1.0"] = "1.0"
    producer_event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utcnow)
    decided_by: str | None = None
    decided_at: datetime | None = None
    distance: int | None = Field(default=None, ge=0)
    reason: str | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        """Prevent unversioned evidence, untyped presence, and non-pair duplicate claims."""
        require_version(self.subject)
        definition = predicate(self.predicate)
        self._validate_subject(definition)
        if self.created_at.tzinfo is None or (
            self.decided_at is not None and self.decided_at.tzinfo is None
        ):
            msg = "Evidence timestamps must include a UTC offset"
            raise ValueError(msg)
        if self.predicate == "near_duplicate_of":
            self._validate_duplicate()
        elif definition.object_kind == "asset":
            self._validate_asset(definition)
        elif not isinstance(self.object, EvidenceValue):
            msg = "Existence assertions require a three-state EvidenceValue"
            raise ValueError(msg)
        elif self.object.value == "absent" and self.predicate != "corrupt":
            msg = "Only directly measured corruption may assert absence"
            raise ValueError(msg)
        elif self.predicate != "corrupt" and not self.object.concept:
            msg = "Concept assertions require a canonical concept identity"
            raise ValueError(msg)
        if self.predicate == "ask.unanswerable" and self.object != EvidenceValue(
            concept="metric", value="unknown"
        ):
            msg = "Unanswerable questions require an unknown metric EvidenceValue"
            raise ValueError(msg)
        return self

    def _validate_subject(self, definition: Predicate) -> None:
        if (
            definition.subject_asset_type is not None
            and self.subject.asset_type != definition.subject_asset_type
        ):
            msg = f"Predicate {self.predicate} requires a {definition.subject_asset_type} subject"
            raise ValueError(msg)
        if self.subject.asset_type == "question" and self.subject.version != self.subject.asset_id:
            msg = "Question subject identity and version must both equal the answer id"
            raise ValueError(msg)

    def _validate_asset(self, definition: Predicate) -> None:
        if not isinstance(self.object, AssetRef):
            msg = "Asset predicates require an AssetRef object"
            raise ValueError(msg)  # noqa: TRY004  # Pydantic requires ValueError for field validation.
        require_version(self.object)
        if (
            definition.object_asset_types
            and self.object.asset_type not in definition.object_asset_types
        ):
            msg = (
                f"Predicate {self.predicate} requires object types {definition.object_asset_types}"
            )
            raise ValueError(msg)

    def _validate_duplicate(self) -> None:
        if not isinstance(self.object, AssetRef) or self.distance is None:
            msg = "Near-duplicate assertions require an asset object and measured distance"
            raise ValueError(msg)
        require_version(self.object)
        if self.subject.asset_id >= self.object.asset_id:
            msg = "Near-duplicate assertions require a canonical ordered distinct pair"
            raise ValueError(msg)


class AssertionDecision(BoundaryModel):
    """Record an immutable status or cache-invalidation audit entry."""

    id: str = Field(default_factory=new_id)
    assertion_id: str
    action: Literal["accept", "reject", "restore", "invalidate"]
    previous_status: AssertionStatus
    status: AssertionStatus
    actor: str
    reason: str
    occurred_at: datetime = Field(default_factory=utcnow)
    producer_event_id: str | None = None


class AssertionDecisionRequest(BoundaryModel):
    """Apply one audited human decision to an exact set of assertion identities."""

    assertion_ids: tuple[str, ...] = Field(min_length=1, max_length=10000)
    status: AssertionStatus
    actor: str = Field(min_length=1)
    reason: str = "User decision"
    idempotency_key: str = Field(min_length=1)
