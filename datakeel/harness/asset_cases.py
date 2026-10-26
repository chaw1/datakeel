# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed an ungranted protected metric without changing any existing golden fixture."""

from pathlib import Path

from datakeel.actions import service
from datakeel.actions.models import ExecuteRequest
from datakeel.core.data_asset_models import DataAssetDefinition
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.storage.data_asset_store import list_assets
from datakeel.storage.database import Database


def seed_asset_case(db: Database, directory: Path) -> CaseFixture:
    """Keep a real SQL-backed metric behind a published request policy with no grant."""
    fixture = seed_enterprise_case(db, directory)
    definition = DataAssetDefinition(
        target=AssetRef(asset_type="metric", asset_id="retail_revenue"),
        name="Controlled retail amount",
        owner="Fixture owner",
        classification="request",
    )
    _execute(
        db, "create_data_asset", JsonDocument({"definition": definition.model_dump(mode="json")})
    )
    asset = next(iter(list_assets(db)))
    _execute(db, "publish_data_asset", JsonDocument({"asset_id": asset.id}))
    return fixture


def _execute(db: Database, action: str, arguments: JsonDocument) -> None:
    plan = service.prepare_action(db, action, arguments)
    run = service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.status != "SUCCEEDED":
        raise ExecutionError(run.error or "Asset golden seed failed")
