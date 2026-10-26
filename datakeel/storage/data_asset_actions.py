# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply typed asset mutations inside the controlled action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.data_asset_parameters import (
    CreateDataAssetParams,
    DataAssetActionParams,
    DataAssetIdentityParams,
    DecideAssetApplicationParams,
    RevokeAssetGrantParams,
    UpdateDataAssetParams,
)
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.data_asset_models import AssetMutationContext
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_grants import (
    decide_application_in_session,
    revoke_grant_in_session,
)
from datakeel.storage.data_asset_store import (
    create_asset_in_session,
    set_status_in_session,
    update_asset_in_session,
)


def execute_data_asset_action(
    session: Session, plan: ActionPlan, params: DataAssetActionParams
) -> OperationResult:
    """Keep domain history, grant changes, and the action receipt in one atomic commit."""
    context = AssetMutationContext(
        actor=plan.actor,
        operation_id=plan.operation_id or plan.id,
        expected_revision=params.expected_revision
        if isinstance(params, DataAssetIdentityParams)
        else None,
    )
    if isinstance(params, CreateDataAssetParams):
        asset = create_asset_in_session(session, params.definition, context)
    elif isinstance(params, UpdateDataAssetParams):
        asset = update_asset_in_session(session, params.asset_id, params.definition, context)
    elif isinstance(params, DataAssetIdentityParams):
        asset = set_status_in_session(
            session,
            params.asset_id,
            "published" if plan.action_type == "publish_data_asset" else "withdrawn",
            context,
        )
    else:
        return _grant_action(session, params, context)
    return OperationResult(
        outputs=[asset.definition.target],
        details={"asset_id": asset.id, "revision": asset.revision, "status": asset.status},
    )


def _grant_action(
    session: Session, params: DataAssetActionParams, context: AssetMutationContext
) -> OperationResult:
    if isinstance(params, DecideAssetApplicationParams):
        application = decide_application_in_session(
            session, params.application_id, context, approved=params.approve
        )
        return OperationResult(
            outputs=[AssetRef(asset_type="data_asset", asset_id=application.asset_id)],
            details={
                "application_id": application.id,
                "asset_id": application.asset_id,
                "status": application.status,
                "grant_id": application.grant_id,
                "reason": params.reason,
            },
        )
    if isinstance(params, RevokeAssetGrantParams):
        grant = revoke_grant_in_session(session, params.grant_id, context)
        return OperationResult(
            outputs=[AssetRef(asset_type="data_asset", asset_id=grant.asset_id)],
            details={"grant_id": grant.id, "asset_id": grant.asset_id, "reason": params.reason},
        )
    msg = "Unknown data asset mutation parameters"
    raise ValidationError(msg)
