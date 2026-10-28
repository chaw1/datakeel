# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze asset mutation state separately from legacy file manifests."""

from sqlalchemy.orm import Session

from datakeel.actions.data_asset_parameters import (
    CreateDataAssetParams,
    DataAssetActionParams,
    DataAssetIdentityParams,
    DecideAssetApplicationParams,
    RevokeAssetGrantParams,
    UpdateDataAssetParams,
)
from datakeel.core.catalog_canonical import document_hash
from datakeel.core.errors import ConflictError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.storage.data_asset_grants import application_in_session, grant_in_session
from datakeel.storage.data_asset_store import asset_in_session, validate_target

_GRANT_REQUIRED = frozenset({"request", "restricted"})


def relaxes_asset_access(session: Session, params: BoundaryModel) -> bool:
    """Opening an active protected asset to every reader needs the review a grant needs."""
    if not isinstance(params, UpdateDataAssetParams):
        return False
    current = asset_in_session(session, params.asset_id)
    return (
        current.status != "draft"
        and current.definition.classification in _GRANT_REQUIRED
        and params.definition.classification not in _GRANT_REQUIRED
    )


def prepare_data_asset_params(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Resolve existing resources and freeze asset revisions before a plan is approved."""
    if isinstance(params, CreateDataAssetParams):
        validate_target(session, params.definition.target)
    if isinstance(params, DataAssetIdentityParams):
        asset = asset_in_session(session, params.asset_id)
        if params.expected_revision is not None and params.expected_revision != asset.revision:
            msg = "Data asset revision changed before preparation"
            raise ConflictError(msg)
        return params.model_copy(update={"expected_revision": asset.revision})
    if isinstance(params, DecideAssetApplicationParams):
        application_in_session(session, params.application_id)
    if isinstance(params, RevokeAssetGrantParams):
        grant_in_session(session, params.grant_id)
    return params


def data_asset_state(session: Session, params: DataAssetActionParams) -> str:
    """Bind the exact mutable asset, pending request, or grant to the plan digest."""
    if isinstance(params, DataAssetIdentityParams):
        value = asset_in_session(session, params.asset_id)
    elif isinstance(params, DecideAssetApplicationParams):
        value = application_in_session(session, params.application_id)
    elif isinstance(params, RevokeAssetGrantParams):
        value = grant_in_session(session, params.grant_id)
    else:
        return document_hash(JsonDocument({}))
    return document_hash(JsonDocument.model_validate(value.model_dump(mode="json")))
