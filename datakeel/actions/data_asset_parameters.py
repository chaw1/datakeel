# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed market mutations bound to the existing controlled-action lifecycle."""

from pydantic import Field

from datakeel.core.data_asset_models import DataAssetDefinition
from datakeel.core.models import BoundaryModel


class DataAssetActionParams(BoundaryModel):
    """Mark asset mutations whose state is independent of file selections."""


class CreateDataAssetParams(DataAssetActionParams):
    """Create a draft card for an existing local dataset, table, or metric."""

    definition: DataAssetDefinition


class DataAssetIdentityParams(DataAssetActionParams):
    """Bind publication changes to a server-frozen asset revision."""

    asset_id: str = Field(min_length=1)
    expected_revision: int | None = Field(default=None, ge=1)


class UpdateDataAssetParams(DataAssetIdentityParams):
    """Replace a draft or published card while retaining every prior revision."""

    definition: DataAssetDefinition


class DecideAssetApplicationParams(DataAssetActionParams):
    """Approve or reject an exact pending request after a human action decision."""

    application_id: str = Field(min_length=1)
    approve: bool
    reason: str = Field(default="", max_length=2000)


class RevokeAssetGrantParams(DataAssetActionParams):
    """Revoke an exact grant through a separately approved audited action."""

    grant_id: str = Field(min_length=1)
    reason: str = Field(default="", max_length=2000)


DATA_ASSET_PARAMETER_TYPES: dict[str, type[BoundaryModel]] = {
    "create_data_asset": CreateDataAssetParams,
    "update_data_asset": UpdateDataAssetParams,
    "publish_data_asset": DataAssetIdentityParams,
    "withdraw_data_asset": DataAssetIdentityParams,
    "decide_asset_application": DecideAssetApplicationParams,
    "revoke_asset_grant": RevokeAssetGrantParams,
}
