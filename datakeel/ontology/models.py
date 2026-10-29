# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned ontology definitions and frozen asset selection contracts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datakeel.core.data_asset_models import SkippedEntries
from datakeel.core.evidence_models import AssertionStatus, PredicateId, Presence
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.core.object_kinds import LEGACY_OBJECT_KINDS, ObjectKind, validate_object_kind


class IdentityMapping(BoundaryModel):
    """Map a public property identity into the existing AssetRef vocabulary."""

    asset_type: ObjectKind
    id_field: str = "id"
    version_field: str | None = None
    namespace: str = "default"

    @field_validator("asset_type")
    @classmethod
    def validate_kind(cls, kind: str) -> str:
        """Require a registered identity kind at load time."""
        return validate_object_kind(kind)


class ObjectType(BoundaryModel):
    """Describe one versioned asset object without duplicating its facts."""

    id: ObjectKind
    version: str = "1.0"
    properties: JsonDocument
    identity_mapping: IdentityMapping
    description: str

    @field_validator("id")
    @classmethod
    def validate_kind(cls, kind: str) -> str:
        """Require a registered object definition identity."""
        return validate_object_kind(kind)


class LinkType(BoundaryModel):
    """Declare relationship semantics separately from transformation provenance."""

    id: str
    version: str = "1.0"
    domain: list[ObjectKind]
    range: list[ObjectKind]
    cardinality: Literal["one-to-one", "one-to-many", "many-to-many"]
    semantics: str
    description: str

    @field_validator("domain", "range")
    @classmethod
    def validate_kinds(cls, kinds: list[str]) -> list[str]:
        """Reject link endpoints whose kinds have not been registered."""
        return [validate_object_kind(kind) for kind in kinds]


class FunctionType(BoundaryModel):
    """Describe a read-only function and its validated input/output schemas."""

    id: str
    version: str = "1.0"
    input_schema: JsonDocument
    output_schema: JsonDocument
    read_scope: str
    handler: str


class ActionType(BoundaryModel):
    """Declare a controlled mutation's schema, policy, and observable effects."""

    id: str
    version: str = "1.0"
    params_schema: JsonDocument
    auth_scope: str
    preconditions: list[str]
    effects: list[str]
    reversible: bool
    inverse_of: str | None = None
    handler: str


class OntologyRegistry(BoundaryModel):
    """Expose the complete versioned interface registry."""

    version: str = "1.0"
    object_types: list[ObjectType]
    link_types: list[LinkType]
    functions: list[FunctionType]
    actions: list[ActionType]


class PropertyFilter(BoundaryModel):
    """Constrain one public property using an explicit bounded operator."""

    field: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
    operator: Literal["eq", "ne", "lt", "lte", "gt", "gte", "contains", "in"] = "eq"
    value: JsonValue

    @model_validator(mode="after")
    def validate_operand(self) -> Self:
        """Reject operators whose operand cannot express their declared predicate."""
        if self.operator == "in" and not isinstance(self.value, list):
            msg = "The in operator requires a JSON array"
            raise ValueError(msg)
        if self.operator in {"lt", "lte", "gt", "gte"} and (
            isinstance(self.value, bool) or not isinstance(self.value, int | float)
        ):
            msg = "Ordered property filters require a numeric value"
            raise ValueError(msg)
        return self


class AssertionFilter(BoundaryModel):
    """Match reviewed concept observations or explicit nonexistence of such observations."""

    predicate: PredicateId
    concept: str | None = Field(default=None, min_length=1)
    value: Presence | None = None
    status: list[AssertionStatus] = Field(
        default_factory=lambda: ["candidate", "accepted"], min_length=1, max_length=3
    )
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    operator: Literal["exists", "not_exists"] = "exists"

    @model_validator(mode="after")
    def validate_predicate(self) -> Self:
        """Reject duplicate states and concept/value operands on asset-to-asset edges."""
        if len(set(self.status)) != len(self.status):
            msg = "Assertion statuses must be unique"
            raise ValueError(msg)
        if self.predicate == "near_duplicate_of" and (self.concept or self.value):
            msg = "Near-duplicate filters select asset relationships, not concept values"
            raise ValueError(msg)
        return self


class ObjectSet(BoundaryModel):
    """Select assets by type, public properties, quality, and version interval."""

    schema_version: Literal["1.0", "1.1"] = "1.1"
    object_type: ObjectKind = "file"
    namespace: Literal["default"] = "default"
    dataset_id: str | None = None
    filters: list[PropertyFilter] = Field(default_factory=list[PropertyFilter], max_length=32)
    quality_min: float | None = Field(default=None, ge=0, le=100)
    quality_max: float | None = Field(default=None, ge=0, le=100)
    version_ids: list[str] = Field(default_factory=list[str], max_length=100)
    created_after: datetime | None = None
    created_before: datetime | None = None
    include_deleted: bool = False
    limit: int = Field(default=1000, ge=1, le=10000)
    assertion_filters: list[AssertionFilter] = Field(
        default_factory=list[AssertionFilter], max_length=32, exclude_if=lambda value: not value
    )
    split: Literal["train", "val", "test"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    has_near_duplicate_in: Literal["train", "val", "test"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator("object_type")
    @classmethod
    def validate_selection_kind(cls, kind: str) -> str:
        """Keep frozen selections restricted to the original five asset kinds."""
        validate_object_kind(kind)
        if kind not in LEGACY_OBJECT_KINDS:
            msg = "Catalog objects cannot participate in frozen asset selections"
            raise ValueError(msg)
        return kind

    @model_validator(mode="after")
    def validate_evidence_version(self) -> Self:
        """Preserve old manifest serialization without silently dropping new predicates."""
        if self.assertion_filters or self.split or self.has_near_duplicate_in:
            if self.schema_version == "1.0":
                msg = "Evidence selection requires ObjectSet schema_version 1.1"
                raise ValueError(msg)
            if self.object_type not in {"file", "artifact"}:
                msg = "Evidence selection requires file or artifact objects"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        """Reject reversed quality/time intervals and ambiguous naive timestamps."""
        if (
            self.quality_min is not None
            and self.quality_max is not None
            and self.quality_min > self.quality_max
        ):
            msg = "quality_min must not exceed quality_max"
            raise ValueError(msg)
        for timestamp in (self.created_after, self.created_before):
            if timestamp is not None and timestamp.tzinfo is None:
                msg = "Version timestamps must include a UTC offset"
                raise ValueError(msg)
        if self.created_after and self.created_before and self.created_after > self.created_before:
            msg = "created_after must not exceed created_before"
            raise ValueError(msg)
        return self


class FrozenObject(BoundaryModel):
    """Bind an asset identity to immutable content and the observed mutable state."""

    asset_ref: AssetRef
    revision: str
    state_revision: int = 0
    properties: dict[str, JsonValue]
    size: int = Field(default=0, ge=0)


class FrozenManifest(BoundaryModel):
    """Freeze exact object revisions for subsequent authorization and execution."""

    query: ObjectSet
    objects: list[FrozenObject]
    state_digest: str
    total_bytes: int = Field(ge=0)
    truncated: bool = False


class FunctionResult(BoundaryModel):
    """Return replayable read results and explicit identities for tool auditing."""

    function: str
    asset_refs: list[AssetRef]
    data: JsonValue
    # Listings name protected entries they left out; absent when nothing was skipped.
    skipped: SkippedEntries | None = None
