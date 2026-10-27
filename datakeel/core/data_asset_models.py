# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen contracts for published data assets, grants, and append-only usage."""

from datetime import datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument

type AssetClassification = Literal["public", "internal", "request", "restricted"]
type AssetStatus = Literal["draft", "published", "withdrawn"]
type AccessScope = Literal["query", "export", "download"]
type AccessEntry = Literal["ask", "export", "download", "mcp", "agent"]
type AssetSort = Literal["popular", "freshness", "quality", "downstream", "name"]


class DataAssetDefinition(BoundaryModel):
    """Package an existing resource with business-facing, sanitized documentation."""

    target: AssetRef
    name: str = Field(min_length=1, max_length=200)
    name_en: str = ""
    description: str = ""
    owner: str = Field(min_length=1)
    classification: AssetClassification = "internal"
    tags: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    scenarios: tuple[str, ...] = ()
    instructions: str = ""
    sample: str = ""

    @model_validator(mode="after")
    def supported_target(self) -> Self:
        """Limit publication to the three supported existing resource kinds."""
        if self.target.asset_type not in {"dataset", "table", "metric"}:
            msg = "Data assets must reference a dataset, table, or metric"
            raise ValueError(msg)
        if self.target.namespace != "default" or not self.target.asset_id.strip():
            msg = "Data assets require a resource in the default namespace"
            raise ValueError(msg)
        return self


class DataAsset(BoundaryModel):
    """Expose one current asset revision without mutable persistence records."""

    id: str
    revision: int = Field(ge=1)
    definition: DataAssetDefinition
    status: AssetStatus = "draft"
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AssetMutationContext(BoundaryModel):
    """Attribute an idempotent controlled mutation to its frozen operation."""

    actor: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    expected_revision: int | None = Field(default=None, ge=1)


class AssetHistory(BoundaryModel):
    """Retain an immutable full asset snapshot for every controlled revision."""

    id: str
    asset_id: str
    operation_id: str
    actor: str
    action: str
    occurred_at: AwareDatetime
    asset: DataAsset


class AssetApplicationInput(BoundaryModel):
    """Request explicit scopes until an aware, bounded expiry time."""

    asset_id: str
    purpose: str = Field(min_length=1, max_length=4000)
    scopes: tuple[AccessScope, ...] = Field(min_length=1)
    expires_at: AwareDatetime


class AssetApplication(BoundaryModel):
    """Track a usage request and its explicit controlled approval decision."""

    id: str
    asset_id: str
    applicant: str
    purpose: str
    scopes: tuple[AccessScope, ...]
    expires_at: AwareDatetime
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: AwareDatetime
    decided_at: AwareDatetime | None = None
    decided_by: str | None = None
    grant_id: str | None = None


class AssetGrant(BoundaryModel):
    """Authorize exactly one subject, asset, and set of scopes until expiry."""

    id: str
    application_id: str
    asset_id: str
    subject: str
    scopes: tuple[AccessScope, ...]
    expires_at: AwareDatetime
    created_at: AwareDatetime
    granted_by: str
    revoked_at: AwareDatetime | None = None
    revoked_by: str | None = None


class AccessContext(BoundaryModel):
    """Carry the existing operator identity and actual data-reading entry point."""

    actor: str = Field(min_length=1)
    entry: AccessEntry
    scope: AccessScope


class SkippedEntries(BoundaryModel):
    """Identify entries a list-style read left out because the caller lacks a grant.

    Only entry and asset identifiers are reported, never the skipped content.
    """

    count: int = Field(ge=1)
    ids: list[str]
    assets: list[str]
    reason: str


class AssetUsage(BoundaryModel):
    """Record one allowed asset use; stored records can never be updated or deleted."""

    id: str
    asset_id: str
    actor: str
    entry: AccessEntry
    scope: AccessScope
    occurred_at: AwareDatetime
    grant_id: str | None = None


class AssetUsageQuery(BoundaryModel):
    """Filter immutable usage by asset and/or actor with a bounded result limit."""

    asset_id: str | None = None
    actor: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class AssetMarketQuery(BoundaryModel):
    """Search names, synonyms, tags and owners using case-insensitive substrings."""

    search: str = ""
    classification: AssetClassification | None = None
    tag: str | None = None
    status: AssetStatus | None = "published"
    sort: AssetSort = "popular"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


class QualityPoint(BoundaryModel):
    """Associate a measured quality score with its evidence timestamp."""

    occurred_at: AwareDatetime
    score: float


class DataAssetCard(BoundaryModel):
    """Aggregate measured quality, lineage, freshness and factual usage statistics."""

    asset: DataAsset
    quality_score: float | None = None
    quality_trend: tuple[QualityPoint, ...] = ()
    upstream: tuple[AssetRef, ...] = ()
    downstream: tuple[AssetRef, ...] = ()
    updated_at: AwareDatetime | None = None
    related_metrics: tuple[AssetRef, ...] = ()
    usage_count: int = 0
    user_count: int = 0
    downstream_count: int = 0
    freshness_seconds: float | None = None
    version_release: JsonDocument | None = None
    standard_coverage: float | None = None


class AssetMarketPage(BoundaryModel):
    """Return deterministic market ordering and the complete matching count."""

    items: tuple[DataAssetCard, ...]
    total: int
    offset: int
    limit: int


class AssetRanking(BoundaryModel):
    """Configure the popular ordering's factual weighted score and stable ties.

    Popular score is uses * usage_weight + users * users_weight + downstream
    dependencies * downstream_weight. Ties use resource update descending and
    asset ID ascending. Other sorts use their named value then these same ties.
    """

    usage_weight: float = Field(default=1, ge=0, allow_inf_nan=False)
    users_weight: float = Field(default=2, ge=0, allow_inf_nan=False)
    downstream_weight: float = Field(default=1, ge=0, allow_inf_nan=False)


class AssetControlEvent(BoundaryModel):
    """Preserve append-only application and grant decisions alongside asset history."""

    id: str
    asset_id: str
    subject_id: str
    operation_id: str
    actor: str
    action: str
    occurred_at: datetime
