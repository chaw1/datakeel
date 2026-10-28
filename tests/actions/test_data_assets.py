# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Asset publication and authorization share signed plans and transactional history."""

from datetime import timedelta
from pathlib import Path

import pytest

from datakeel.actions.data_asset_parameters import (
    CreateDataAssetParams,
    DataAssetIdentityParams,
    UpdateDataAssetParams,
)
from datakeel.actions.models import ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.references import parameter_refs
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.data_asset_models import AssetApplicationInput, DataAsset, DataAssetDefinition
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.core.models import AssetRef, JsonDocument, utcnow
from datakeel.storage.data_asset_grants import (
    control_history,
    get_application,
    get_grant,
    list_grants,
    submit_application,
)
from datakeel.storage.data_asset_store import asset_history, get_asset, list_assets
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths


def _execute(db: Database, plan: ActionPlan, *, approve: bool = False) -> None:
    if approve:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"


def _prepare(db: Database, action: str, params: dict[str, object]) -> ActionPlan:
    return prepare_action(db, action, JsonDocument.model_validate(params))


@pytest.fixture
def asset(db: Database, tmp_path: Path) -> DataAsset:
    """Create an independent generated dataset and its controlled asset draft."""
    path = tmp_path / "source.txt"
    path.write_text("Generated asset fixture", encoding="utf-8")
    dataset = import_paths(db, "Asset fixture", [path])
    plan = _prepare(
        db,
        "create_data_asset",
        {
            "definition": DataAssetDefinition(
                target=AssetRef(asset_id=dataset.id),
                name="Revenue fixture",
                owner="local",
                classification="request",
            ).model_dump(mode="json")
        },
    )
    assert plan.impact.object_count == 1
    assert plan.manifest.objects == []
    _execute(db, plan)
    return list_assets(db)[0]


def _published(db: Database, asset: DataAsset) -> DataAsset:
    _execute(db, _prepare(db, "publish_data_asset", {"asset_id": asset.id}))
    return get_asset(db, asset.id)


def test_asset_revision_lifecycle_retains_attributed_history(
    db: Database, asset: DataAsset
) -> None:
    """Create, edit, publish and withdraw retain every signed business revision."""
    definition = asset.definition.model_copy(update={"description": "Documented fixture"})
    plan = _prepare(
        db,
        "update_data_asset",
        {"asset_id": asset.id, "definition": definition.model_dump(mode="json")},
    )
    assert plan.canonical_params["expected_revision"] == 1
    _execute(db, plan)
    _published(db, get_asset(db, asset.id))
    _execute(db, _prepare(db, "withdraw_data_asset", {"asset_id": asset.id}))
    history = asset_history(db, asset.id)
    assert [item.asset.status for item in history] == ["draft", "draft", "published", "withdrawn"]
    assert [item.asset.revision for item in history] == [1, 2, 3, 4]
    assert all(item.actor == "local" and item.operation_id for item in history)


def test_asset_changed_revision_rejects_stale_prepared_action(
    db: Database, asset: DataAsset
) -> None:
    """Changing a card after preparation cannot silently execute a stale plan."""
    stale = _prepare(db, "publish_data_asset", {"asset_id": asset.id})
    _execute(db, _prepare(db, "withdraw_data_asset", {"asset_id": asset.id}))
    with pytest.raises(ConflictError, match="state changed"):
        _execute(db, stale)
    with pytest.raises(ConflictError, match="revision changed"):
        _prepare(db, "publish_data_asset", {"asset_id": asset.id, "expected_revision": 1})


def test_access_decision_and_revocation_require_explicit_human_approval(
    db: Database, asset: DataAsset
) -> None:
    """Unsigned decisions issue no grants; approvals and revocations have durable history."""
    published = _published(db, asset)
    application = submit_application(
        db,
        AssetApplicationInput(
            asset_id=published.id,
            purpose="Generated analytics fixture",
            scopes=("query",),
            expires_at=utcnow() + timedelta(hours=1),
        ),
        "reader",
    )
    plan = _prepare(
        db, "decide_asset_application", {"application_id": application.id, "approve": True}
    )
    assert plan.requires_approval
    with pytest.raises(AuthorizationError, match="human approval"):
        _execute(db, plan)
    assert list_grants(db) == ()
    _execute(db, plan, approve=True)
    decision = get_application(db, application.id)
    assert decision.status == "approved"
    assert decision.grant_id is not None
    grant = get_grant(db, decision.grant_id)
    assert grant.subject == "reader"
    revoke = _prepare(db, "revoke_asset_grant", {"grant_id": grant.id, "reason": "Finished"})
    assert revoke.requires_approval
    _execute(db, revoke, approve=True)
    assert get_grant(db, grant.id).revoked_by == "local"
    assert [item.action for item in control_history(db, asset.id)] == [
        "apply",
        "approved",
        "revoke",
    ]


def test_application_rejection_creates_no_authorization(db: Database, asset: DataAsset) -> None:
    """A controlled business rejection remains visible and never creates a grant."""
    _published(db, asset)
    request = submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset.id,
            purpose="Temporary fixture",
            scopes=("query",),
            expires_at=utcnow() + timedelta(hours=1),
        ),
        "reader",
    )
    rejected = _prepare(
        db, "decide_asset_application", {"application_id": request.id, "approve": False}
    )
    _execute(db, rejected, approve=True)
    assert get_application(db, request.id).status == "rejected"
    assert list_grants(db) == ()


def test_asset_action_references_keep_domain_identities(asset: DataAsset) -> None:
    """Publication targets remain discoverable even without a legacy file manifest."""
    assert parameter_refs(CreateDataAssetParams(definition=asset.definition)) == [
        asset.definition.target
    ]
    assert parameter_refs(
        UpdateDataAssetParams(asset_id=asset.id, definition=asset.definition)
    ) == [asset.definition.target]
    assert parameter_refs(DataAssetIdentityParams(asset_id=asset.id))[0].asset_id == asset.id
