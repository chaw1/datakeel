# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Receipts retain distinct authoritative asset kinds when human-readable identities collide."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.models import AssetRef, JsonDocument, new_id

if TYPE_CHECKING:
    from datakeel.actions.models import ActionRun
    from datakeel.storage.database import Database


def test_bind_role_receipt_preserves_user_and_role_with_the_same_identifier(db: Database) -> None:
    """Binding an identically named user and role records both source identities in lineage."""
    _execute(db, "manage_users", {"operation": "create", "user_id": "local"})
    _execute(db, "define_role", {"role_id": "shared", "name": "Shared role", "scopes": []})
    _execute(db, "manage_users", {"operation": "create", "user_id": "shared"})
    result = _execute(
        db,
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "shared",
            "role_id": "shared",
        },
    )
    assert result.receipt is not None
    assert AssetRef(asset_type="user", asset_id="shared") in result.receipt.inputs
    assert AssetRef(asset_type="role", asset_id="shared") in result.receipt.inputs
    assert len(result.receipt.inputs) == 2


def _execute(db: Database, action: str, values: dict[str, object]) -> ActionRun:
    plan = service.prepare_action(
        db, action, JsonDocument.model_validate({"request_id": new_id(), **values})
    )
    if plan.requires_approval:
        service.approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest)
        )
    return service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
