# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Asset market, requests, grants and immutable publication and usage history."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, Field

from datakeel.api.dependencies import DatabaseDependency
from datakeel.assets.service import get_asset_card, search_market
from datakeel.core.data_asset_models import (
    AccessScope,
    AssetApplication,
    AssetApplicationInput,
    AssetControlEvent,
    AssetGrant,
    AssetHistory,
    AssetMarketPage,
    AssetMarketQuery,
    AssetUsage,
    AssetUsageQuery,
    DataAssetCard,
)
from datakeel.core.models import BoundaryModel
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.data_asset_grants import (
    control_history,
    get_application,
    get_grant,
    list_applications,
    list_grants,
    submit_application,
)
from datakeel.storage.data_asset_store import asset_history

router = APIRouter(prefix="/api/data-assets", tags=["data-assets"])


class AssetApplicationCreate(BoundaryModel):
    """Carry the existing local operator identity and requested usage terms."""

    applicant: str = Field(default="local-user", min_length=1)
    purpose: str = Field(min_length=1, max_length=4000)
    scopes: tuple[AccessScope, ...] = Field(min_length=1)
    expires_at: AwareDatetime
    operation_id: str | None = Field(default=None, min_length=1)


@router.get("")
def market(
    query: Annotated[AssetMarketQuery, Query()],
    db: DatabaseDependency,
    *,
    include_unpublished: bool = False,
) -> AssetMarketPage:
    """Search measured asset cards using the declared deterministic sort contract."""
    selected = query.model_copy(update={"status": None}) if include_unpublished else query
    return search_market(db, selected)


@router.get("/applications")
def applications(
    db: DatabaseDependency, asset_id: str | None = None, applicant: str | None = None
) -> tuple[AssetApplication, ...]:
    """Read request progress by asset or the existing operator identity."""
    return list_applications(db, asset_id, applicant)


@router.get("/applications/{application_id}")
def application(application_id: str, db: DatabaseDependency) -> AssetApplication:
    """Read one durable request and its granted authorization identity."""
    return get_application(db, application_id)


@router.get("/grants")
def grants(
    db: DatabaseDependency, asset_id: str | None = None, subject: str | None = None
) -> tuple[AssetGrant, ...]:
    """Read issued grants, retaining revoked and expired records as history."""
    return list_grants(db, asset_id, subject)


@router.get("/grants/{grant_id}")
def grant(grant_id: str, db: DatabaseDependency) -> AssetGrant:
    """Read the exact granted scope, expiry, subject and revocation attribution."""
    return get_grant(db, grant_id)


@router.get("/audit")
def audit(
    query: Annotated[AssetUsageQuery, Query()], db: DatabaseDependency
) -> tuple[AssetUsage, ...]:
    """Filter append-only allowed uses by asset and operator."""
    return list_usage(db, query)


@router.get("/{asset_id}/history")
def history(asset_id: str, db: DatabaseDependency) -> tuple[AssetHistory, ...]:
    """Read every frozen card revision and its controlled operation attribution."""
    return asset_history(db, asset_id)


@router.get("/{asset_id}/control-history")
def controls(asset_id: str, db: DatabaseDependency) -> tuple[AssetControlEvent, ...]:
    """Read append-only request and authorization decisions for an asset."""
    return control_history(db, asset_id)


@router.get("/{asset_id}/applications")
def asset_applications(asset_id: str, db: DatabaseDependency) -> tuple[AssetApplication, ...]:
    """Read the request and approval progress displayed beside a card."""
    return list_applications(db, asset_id=asset_id)


@router.post("/{asset_id}/applications", status_code=201)
def apply(asset_id: str, body: AssetApplicationCreate, db: DatabaseDependency) -> AssetApplication:
    """Submit a purpose and bounded expiry; approval remains a controlled action."""
    return submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset_id,
            purpose=body.purpose,
            scopes=body.scopes,
            expires_at=body.expires_at,
        ),
        body.applicant,
        operation_id=body.operation_id,
    )


@router.get("/{asset_id}")
def card(asset_id: str, db: DatabaseDependency) -> DataAssetCard:
    """Aggregate current quality, lineage, freshness, related metrics and usage."""
    return get_asset_card(db, asset_id)
