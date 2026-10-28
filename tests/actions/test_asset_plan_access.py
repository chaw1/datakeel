# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled plans and receipts cannot expose data after source access is withdrawn."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlalchemy import func, select

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessContext, AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.action_rows import ActionPlanRow, ApprovalRow
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.assets.action_helpers import ActionSource, seed_action_source, source_params
from tests.assets.entry_helpers import GrantState, grant, publish, revoke


def _mcp_prepare(db: Database, params: JsonDocument) -> ToolOutcome:
    async def run() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool("quarantine_files", params.root, raise_on_error=False)
            return ToolOutcome.model_validate(response.structured_content)

    return asyncio.run(run())


@pytest.mark.parametrize("state", ["none", "expired", "revoked", "wrong_scope", "valid"])
def test_action_preparation_enforces_source_policy_in_every_entry(
    db: Database, state: GrantState
) -> None:
    """Direct, HTTP, Agent and real MCP preparations never return unauthorized frozen captions."""
    source = seed_action_source(db)
    grant(db, source.asset, state, "query")
    params = source_params(source)
    if state == "valid":
        assert (
            source.marker
            in service.prepare_action(db, "quarantine_files", params).model_dump_json()
        )
    else:
        with pytest.raises(AuthorizationError, match="apply for access"):
            service.prepare_action(db, "quarantine_files", params)
    with TestClient(create_app(db)) as client:
        response = client.post("/api/actions/quarantine_files/prepare", json=params.root)
        assert response.status_code == (200 if state == "valid" else 403)
        assert (source.marker in response.text) == (state == "valid")
    for result in (
        invoke_tool(db, "quarantine_files", params, ToolCallContext()),
        _mcp_prepare(db, params),
    ):
        assert result.status == ("SUCCEEDED" if state == "valid" else "FAILED")
        assert (source.marker in result.model_dump_json()) == (state == "valid")
    usages = list_usage(db, AssetUsageQuery(asset_id=source.asset.id))
    assert len(usages) == (4 if state == "valid" else 0)
    if state == "valid":
        assert {item.entry for item in usages} == {"ask", "agent", "mcp"}
    else:
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(ActionPlanRow)) == 0


def test_export_plan_requires_only_export_grant_through_approval_and_execution(
    db: Database,
) -> None:
    """An export grant authorizes its source manifest without an unrelated query grant."""
    source = seed_action_source(db)
    grant(db, source.asset, "valid", "export")
    plan = service.prepare_action(
        db, "export_dataset", JsonDocument({"dataset_id": source.dataset_id})
    )
    assert source.marker in plan.model_dump_json()
    service.approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"
    assert service.get_plan(db, plan.id).id == plan.id
    usages = list_usage(db, AssetUsageQuery(asset_id=source.asset.id))
    assert len(usages) == 4
    assert all(item.scope == "export" for item in usages)


def test_action_prepare_cannot_borrow_a_different_access_subject(db: Database) -> None:
    """The action's actual actor controls source access even if an internal caller errs."""
    source = seed_action_source(db)
    grant(db, source.asset, "valid", "query", subject="entitled")
    with pytest.raises(AuthorizationError, match="apply for access"):
        service.prepare_action(
            db,
            "quarantine_files",
            source_params(source),
            ActionContext(actor="visitor"),
            access=AccessContext(actor="entitled", entry="agent", scope="query"),
        )


def test_mcp_export_plan_keeps_actual_entry_and_export_scope(db: Database) -> None:
    """The real MCP control chain records one export use per successful source response."""
    source = seed_action_source(db)
    grant(db, source.asset, "valid", "export")

    async def run() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            prepared = await client.call_tool("export_dataset", {"dataset_id": source.dataset_id})
            outcome = ToolOutcome.model_validate(prepared.structured_content)
            assert outcome.plan is not None
            assert source.marker in outcome.model_dump_json()
            arguments = {"plan_id": outcome.plan.id, "plan_digest": outcome.plan.plan_digest}
            for name in ("approve_plan", "execute_plan"):
                params = {**arguments, "approve": True} if name == "approve_plan" else arguments
                response = await client.call_tool(name, params)
                assert ToolOutcome.model_validate(response.structured_content).status == "SUCCEEDED"

    asyncio.run(run())
    usages = list_usage(db, AssetUsageQuery(asset_id=source.asset.id))
    assert len(usages) == 3
    assert {(item.entry, item.scope) for item in usages} == {("mcp", "export")}


def _denied_history(db: Database, source: ActionSource, plan_id: str) -> None:
    with pytest.raises(AuthorizationError, match="apply for access"):
        service.get_plan(db, plan_id)
    assert service.list_runs(db) == []
    with TestClient(create_app(db)) as client:
        response = client.get(f"/api/actions/plans/{plan_id}")
        assert response.status_code == 403
        assert source.marker not in response.text
        runs = client.get("/api/actions/runs")
        assert runs.status_code == 200
        assert runs.json() == []


def test_revoked_source_denies_plan_receipt_and_operation_replays(db: Database) -> None:
    """Current grants protect saved plans, prior metadata receipts and cached tool outcomes."""
    source = seed_action_source(db)
    grant_id = grant(db, source.asset, "valid", "query")
    assert grant_id is not None
    params = JsonDocument({"dataset_id": source.dataset_id, "values": {}, "reason": "Generated"})
    context = ToolCallContext(session_id="action-source-session")
    prepared = invoke_tool(db, "save_metadata", params, context, call_id="prepare")
    assert prepared.plan is not None
    plan = prepared.plan
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    execute_params = JsonDocument(
        {"plan_id": plan.id, "plan_digest": plan.plan_digest, "operation_id": plan.operation_id}
    )
    executed = invoke_tool(db, "execute_plan", execute_params, context, call_id="execute")
    assert executed.run is not None
    assert executed.run.receipt is not None
    assert source.marker in executed.run.receipt.model_dump_json()
    assert invoke_tool(db, "save_metadata", params, context, call_id="prepare").plan == plan
    assert (
        invoke_tool(db, "execute_plan", execute_params, context, call_id="execute").run
        == executed.run
    )
    revoke(db, grant_id)
    _denied_history(db, source, plan.id)
    with pytest.raises(AuthorizationError, match="apply for access"):
        service.execute_plan(db, plan.id, request)
    cached = invoke_tool(db, "save_metadata", params, context, call_id="prepare")
    assert cached.status == "FAILED"
    assert cached.plan is None
    assert cached.content.root == {}
    cached_run = invoke_tool(db, "execute_plan", execute_params, context, call_id="execute")
    assert cached_run.status == "FAILED"
    assert cached_run.run is None
    assert cached_run.content.root == {}


def test_revocation_prevents_approval_manifest_and_pending_collection_disclosure(
    db: Database,
) -> None:
    """An approval decision cannot re-emit old source text after its reading grant is revoked."""
    source = seed_action_source(db)
    grant_id = grant(db, source.asset, "valid", "query")
    assert grant_id is not None
    plan = service.prepare_action(db, "delete_files", source_params(source))
    revoke(db, grant_id)
    with pytest.raises(AuthorizationError, match="apply for access"):
        service.approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest)
        )
    assert service.list_approvals(db) == []
    with TestClient(create_app(db)) as client:
        response = client.get("/api/approvals")
        assert response.status_code == 200
        assert response.json() == []
    with db.session() as session:
        assert session.query(ApprovalRow).filter_by(plan_id=plan.id).first() is None


def test_revoked_private_history_is_filtered_without_blocking_public_workbench(
    db: Database, tmp_path: Path
) -> None:
    """Collections remain available and audit only returned public sources after revocation."""
    source = seed_action_source(db)
    grant_id = grant(db, source.asset, "valid", "query")
    assert grant_id is not None
    private = service.prepare_action(db, "delete_files", source_params(source))
    metadata = service.prepare_action(
        db,
        "save_metadata",
        JsonDocument({"dataset_id": source.dataset_id, "values": {}, "reason": "Fixture"}),
    )
    service.execute_plan(db, metadata.id, ExecuteRequest(plan_digest=metadata.plan_digest))
    path = tmp_path / "public.txt"
    path.write_text("Generated public data", encoding="utf-8")
    public = import_paths(db, "Public source", [path])
    public_asset = publish(db, AssetRef(asset_id=public.id), "public")
    public_runs: set[str] = set()
    for ordinal in range(2):
        plan = service.prepare_action(
            db,
            "save_metadata",
            JsonDocument(
                {"dataset_id": public.id, "values": {"revision": ordinal}, "reason": "Fixture"}
            ),
        )
        public_runs.add(
            service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).id
        )
    pending = service.prepare_action(
        db, "delete_files", JsonDocument({"selection": {"dataset_id": public.id}})
    )
    revoke(db, grant_id)
    before = len(list_usage(db, AssetUsageQuery(asset_id=public_asset.id)))
    with TestClient(create_app(db)) as client:
        response = client.get("/api/actions/runs")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == public_runs
        assert source.marker not in response.text
        assert len(list_usage(db, AssetUsageQuery(asset_id=public_asset.id))) == before + 1
        response = client.get("/api/approvals")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [pending.id]
        assert client.get(f"/api/actions/plans/{private.id}").status_code == 403
