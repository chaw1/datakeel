# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Opening a protected asset to every reader cannot bypass human review."""

from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.agent.confirm import execute_reversible
from datakeel.core.data_asset_models import AssetClassification, DataAsset
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_store import get_asset
from datakeel.storage.database import Database
from tests.assets.entry_helpers import EntryResources, publish, seed_resources


@pytest.fixture
def resources(db: Database, tmp_path: Path) -> EntryResources:
    """Seed one generated downloadable dataset for the protected policy."""
    return seed_resources(db, tmp_path)


def _update(asset: DataAsset, classification: AssetClassification) -> JsonDocument:
    definition = asset.definition.model_copy(update={"classification": classification})
    return JsonDocument({"asset_id": asset.id, "definition": definition.model_dump(mode="json")})


def _search(db: Database, resources: EntryResources, call_id: str) -> str:
    context = ToolCallContext(session_id="relaxation")
    arguments = JsonDocument({"dataset_id": resources.dataset_id})
    return invoke_tool(db, "search_files", arguments, context, call_id=call_id).status


@pytest.mark.parametrize("before", ["request", "restricted"])
@pytest.mark.parametrize("after", ["public", "internal"])
def test_agent_relaxing_protected_asset_requires_human_approval(
    db: Database,
    resources: EntryResources,
    before: AssetClassification,
    after: AssetClassification,
) -> None:
    """An Agent-prepared downgrade is not auto-executed and the data stays protected."""
    asset = publish(db, AssetRef(asset_id=resources.dataset_id), before)
    context = ToolCallContext(session_id="relaxation")
    outcome = invoke_tool(db, "update_data_asset", _update(asset, after), context, call_id="u")
    assert outcome.status == "SUCCEEDED"
    assert outcome.plan is not None
    assert outcome.requires_approval
    assert execute_reversible(db, outcome, context, dry_run=False) is None
    unapproved = prepare_action(db, "update_data_asset", _update(asset, after))
    with pytest.raises(AuthorizationError):
        execute_plan(db, unapproved.id, ExecuteRequest(plan_digest=unapproved.plan_digest))
    assert get_asset(db, asset.id).definition.classification == before
    assert _search(db, resources, "read-denied") == "FAILED"

    approve_plan(
        db, outcome.plan.id, ApprovalDecision(approve=True, plan_digest=outcome.plan.plan_digest)
    )
    approved = execute_plan(
        db, outcome.plan.id, ExecuteRequest(plan_digest=outcome.plan.plan_digest)
    )
    assert approved.status == "SUCCEEDED"
    assert get_asset(db, asset.id).definition.classification == after
    assert _search(db, resources, "read-approved") == "SUCCEEDED"


@pytest.mark.parametrize(
    ("before", "after"),
    [("restricted", "restricted"), ("restricted", "request"), ("internal", "restricted")],
)
def test_updates_that_keep_or_tighten_protection_stay_reversible(
    db: Database,
    resources: EntryResources,
    before: AssetClassification,
    after: AssetClassification,
) -> None:
    """Documentation edits and stricter classifications keep the existing automatic rule."""
    asset = publish(db, AssetRef(asset_id=resources.dataset_id), before)
    plan = prepare_action(db, "update_data_asset", _update(asset, after))
    assert not plan.requires_approval
