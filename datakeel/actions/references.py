# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose metadata identities without placing them in legacy frozen manifests."""

from datakeel.actions.catalog_parameters import (
    ImportCatalogParams,
    RestoreCatalogParams,
    RollbackMetricParams,
    RollbackTermParams,
    UpdateMetricParams,
    UpdateTermParams,
)
from datakeel.actions.data_asset_parameters import (
    CreateDataAssetParams,
    DataAssetIdentityParams,
    UpdateDataAssetParams,
)
from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import parse_params
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


def parameter_refs(params: BoundaryModel) -> list[AssetRef]:
    """Read typed action targets independently of legacy ObjectSet membership."""
    if isinstance(params, ImportCatalogParams) and params.snapshot is not None:
        return [item.asset_ref for item in params.snapshot.objects]
    if isinstance(params, RestoreCatalogParams):
        return [
            AssetRef(asset_type="source", asset_id=catalog_id(params.scope.removeprefix("source:")))
        ]
    if isinstance(params, UpdateMetricParams):
        return [
            AssetRef(
                asset_type="metric",
                asset_id=params.definition.id,
                version=str(params.definition.version),
            )
        ]
    if isinstance(params, RollbackMetricParams):
        return [
            AssetRef(asset_type="metric", asset_id=params.metric_id, version=str(params.version))
        ]
    return _data_asset_refs(params) + _term_refs(params)


def _data_asset_refs(params: BoundaryModel) -> list[AssetRef]:
    if isinstance(params, CreateDataAssetParams | UpdateDataAssetParams):
        return [params.definition.target]
    if isinstance(params, DataAssetIdentityParams):
        return [AssetRef(asset_type="data_asset", asset_id=params.asset_id)]
    return []


def _term_refs(params: BoundaryModel) -> list[AssetRef]:
    if isinstance(params, UpdateTermParams):
        return [
            AssetRef(
                asset_type="term",
                asset_id=f"term/{params.definition.term}",
                version=str(params.expected_revision),
            )
        ]
    if isinstance(params, RollbackTermParams):
        return [
            AssetRef(
                asset_type="term", asset_id=f"term/{params.term}", version=str(params.revision)
            )
        ]
    return []


def plan_refs(plan: ActionPlan) -> list[AssetRef]:
    """Combine file manifest identities and separately bound metadata targets."""
    params = parse_params(plan.action_type, JsonDocument(plan.canonical_params))
    return [item.asset_ref for item in plan.manifest.objects] + parameter_refs(params)
