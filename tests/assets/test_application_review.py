# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Access applications are decided only by an independent person on the Web UI or CLI."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessEntry, AssetApplicationInput
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, JsonDocument, utcnow
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_grants import application_in_session, submit_application
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.assets.entry_helpers import publish

PERSON_ONLY = "approved or rejected by a person in the Web UI or CLI"
SELF_REVIEW = "cannot review their own access application"


def _application(db: Database, tmp_path: Path, applicant: str) -> str:
    document = tmp_path / "review.txt"
    document.write_text("Generated review sample.")
    dataset = import_paths(db, "Generated review dataset", [document])
    asset = publish(db, AssetRef(asset_id=dataset.id), "restricted")
    return submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset.id,
            purpose="Generated review regression",
            scopes=("query",),
            expires_at=utcnow() + timedelta(days=1),
        ),
        applicant,
    ).id


def _tool(db: Database, entry: AccessEntry, name: str, arguments: JsonDocument) -> ToolOutcome:
    if entry == "agent":
        return invoke_tool(db, name, arguments, ToolCallContext(session_id="review"))

    async def call() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(name, arguments.root, raise_on_error=False)
            return ToolOutcome.model_validate(response.structured_content)

    return asyncio.run(call())


def _status(db: Database, application_id: str) -> str:
    with db.session() as session:
        return application_in_session(session, application_id).status


@pytest.mark.parametrize("entry", ["agent", "mcp"])
def test_tools_cannot_prepare_approve_or_execute_application_decisions(
    db: Database, tmp_path: Path, entry: AccessEntry
) -> None:
    """Tool callers get an explicit refusal at every step; the person keeps the decision."""
    application_id = _application(db, tmp_path, "analyst")
    decision = JsonDocument({"application_id": application_id, "approve": True})
    for approve in (True, False):
        arguments = JsonDocument({"application_id": application_id, "approve": approve})
        prepared = _tool(db, entry, "decide_asset_application", arguments)
        assert prepared.status == "FAILED"
        assert PERSON_ONLY in (prepared.error or "")
    plan = prepare_action(db, "decide_asset_application", decision)
    approval = JsonDocument({"plan_id": plan.id, "plan_digest": plan.plan_digest, "approve": True})
    approved = _tool(db, entry, "approve_plan", approval)
    assert approved.status == "FAILED"
    assert PERSON_ONLY in (approved.error or "")
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execution = JsonDocument({"plan_id": plan.id, "plan_digest": plan.plan_digest})
    executed = _tool(db, entry, "execute_plan", execution)
    assert executed.status == "FAILED"
    assert PERSON_ONLY in (executed.error or "")
    assert _status(db, application_id) == "pending"
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"
    assert _status(db, application_id) == "approved"


@pytest.mark.parametrize("applicant", ["local", " LOCAL "])
@pytest.mark.parametrize("outcome", ["approved", "rejected"])
def test_applicant_cannot_review_own_application_even_with_self_reported_identity(
    db: Database, tmp_path: Path, applicant: str, outcome: str
) -> None:
    """The same operator name, ignoring case and padding, cannot decide its own request."""
    application_id = _application(db, tmp_path, applicant)
    approve = outcome == "approved"
    decision = JsonDocument({"application_id": application_id, "approve": approve})
    with pytest.raises(AuthorizationError, match=SELF_REVIEW):
        prepare_action(db, "decide_asset_application", decision, ActionContext(actor="local"))
    with TestClient(create_app(db), raise_server_exceptions=False) as client:
        response = client.post("/api/actions/decide_asset_application/prepare", json=decision.root)
    assert response.status_code == 403
    assert SELF_REVIEW in response.text
    assert _status(db, application_id) == "pending"
    reviewer = ActionContext(actor="reviewer")
    plan = prepare_action(db, "decide_asset_application", decision, reviewer)
    approve_plan(
        db,
        plan.id,
        ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor="reviewer"),
    )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="reviewer"))
    assert run.status == "SUCCEEDED"
    assert _status(db, application_id) == outcome
