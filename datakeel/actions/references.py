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
from datakeel.actions.models import ActionPlan
from datakeel.actions.parameters import parse_params
from datakeel.actions.standard_parameters import (
    ConfirmStandardMappingParams,
    ImportStandardsParams,
    StandardActionParams,
    UpdateCodeListParams,
    UpdateStandardParams,
)
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


def parameter_refs(params: BoundaryModel) -> list[AssetRef]:
    """Read typed action targets independently of legacy ObjectSet membership."""
    if isinstance(params, StandardActionParams):
        return standard_refs(params)
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
    return _term_refs(params)


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


def standard_refs(params: StandardActionParams) -> list[AssetRef]:
    """Identify standards targets separately from the legacy file manifest contract."""
    if isinstance(params, UpdateStandardParams):
        return [AssetRef(asset_type="standard", asset_id=params.definition.code)]
    if isinstance(params, UpdateCodeListParams):
        return [AssetRef(asset_type="code_list", asset_id=params.definition.code)]
    if isinstance(params, ConfirmStandardMappingParams):
        return [AssetRef(asset_type="column", asset_id=params.mapping.column_id)]
    if isinstance(params, ImportStandardsParams):
        return [
            *(
                AssetRef(asset_type="standard", asset_id=item.code)
                for item in params.contract.standards
            ),
            *(
                AssetRef(asset_type="code_list", asset_id=item.code)
                for item in params.contract.code_lists
            ),
            *(
                AssetRef(asset_type="standard_synonyms", asset_id=item.canonical)
                for item in params.contract.synonyms
            ),
        ]
    return [AssetRef(asset_type="standards", asset_id="contract")]
