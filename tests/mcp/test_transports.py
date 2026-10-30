# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real subprocess pipes and loopback SSE both enforce identical audited controls."""

import asyncio
import socket
import sys
from pathlib import Path

import httpx2
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport
from mcp_types import Implementation, Tool

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.views import DatasetView


async def _call(client: Client, name: str, arguments: JsonDocument) -> ToolOutcome:
    response = await client.call_tool(name, arguments.root, raise_on_error=False)
    result = ToolOutcome.model_validate(response.structured_content)
    assert response.is_error == (result.status == "FAILED")
    return result


def _assert_training_quality_tool(tools: list[Tool]) -> None:
    training = next(tool for tool in tools if tool.name == "get_training_quality")
    assert training.annotations is not None
    assert training.annotations.read_only_hint is True
    assert training.input_schema["required"] == ["dataset_id"]
    assert "version_id" in training.input_schema["properties"]


async def _exercise(client: Client, db: Database, dataset_id: str) -> None:
    assert client.initialize_result is not None
    assert client.initialize_result.protocol_version == "2025-11-25"
    tools = await client.list_tools()
    assert len(tools) == 99 + 2  # TAILS-4: R1 template upgrade, T3 assignees
    _assert_training_quality_tool(tools)
    assert {
        "query_kg",
        "explain_relation",
        "run_kg_extraction",
        "submit_custom_operator",
        "publish_release",
        "training_distribution",
        "training_leakage",
        "clean_training_data",
    } <= {tool.name for tool in tools}
    assert {"list_quality_rules", "get_table_quality", "create_quality_rule"} <= {
        tool.name for tool in tools
    }
    assert {"annotation_quality", "annotation_acceptance"} <= {tool.name for tool in tools}
    read = await _call(client, "list_datasets", JsonDocument({}))
    assert dataset_id in {item.asset_id for item in read.asset_refs}
    selection = JsonDocument({"selection": {"dataset_id": dataset_id, "quality_max": 0}})
    prepared = await _call(client, "delete_files", selection)
    assert prepared.plan is not None
    assert prepared.requires_approval
    assert prepared.plan.impact.object_count == 1
    query = JsonDocument({"dataset_id": dataset_id, "quality_max": 0})
    before = await _call(client, "search_files", query)
    assert sum(item.asset_type == "file" for item in before.asset_refs) == 1
    assert {"approve_plan", "execute_plan"}.isdisjoint(tool.name for tool in tools)
    arguments = JsonDocument(
        {"plan_id": prepared.plan.id, "plan_digest": prepared.plan.plan_digest}
    )
    refused = await _call(client, "approve_plan", JsonDocument({**arguments.root, "approve": True}))
    assert refused.status == "FAILED"
    assert "Web UI or CLI" in (refused.error or "")
    assert (await _call(client, "execute_plan", arguments)).status == "FAILED"
    assert sum(item.asset_type == "file" for item in before.asset_refs) == 1
    # A person approves and executes on the Web UI (recorded as local); the client only prepared.
    decision = ApprovalDecision(
        plan_digest=prepared.plan.plan_digest, approve=True, reason="checked"
    )
    assert approve_plan(db, prepared.plan.id, decision).status == "APPROVED"
    executed = execute_plan(
        db,
        prepared.plan.id,
        ExecuteRequest(plan_digest=prepared.plan.plan_digest),
    )
    assert executed.status == "SUCCEEDED"
    assert executed.receipt is not None
    assert executed.receipt.outputs
    assert "agent:protocol-fixture/session:" in executed.receipt.on_behalf_of
    after = await _call(client, "search_files", query)
    assert all(item.asset_type != "file" for item in after.asset_refs)
    invalid = await _call(client, "get_quality", JsonDocument({"unexpected": 1}))
    assert invalid.status == "FAILED"
    unknown = await _call(client, "not_registered", JsonDocument({"dataset_id": dataset_id}))
    assert unknown.status == "FAILED"


def _assert_audit(db: Database) -> None:
    invocations = list_invocations(db)
    assert len(invocations) == 8
    assert [
        item.status for item in invocations if item.name in {"approve_plan", "execute_plan"}
    ] == [
        "FAILED",
        "FAILED",
    ]
    assert all(item.actor == "local" for item in invocations)
    assert all(item.agent_id == "protocol-fixture" for item in invocations)
    assert len({item.session_id for item in invocations}) == 1
    assert invocations[0].session_id
    assert invocations[0].asset_refs
    assert all(item.completed_at and item.elapsed_ms >= 0 for item in invocations)
    assert [item.status for item in invocations[-2:]] == ["FAILED", "FAILED"]


def test_stdio_when_cli_subprocess_connects_controls_and_audits_real_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spawn the public CLI and share only a fresh local SQLite database with the client."""
    home = tmp_path / "home"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    database_url = f"sqlite:///{tmp_path / 'stdio.db'}"
    db = Database(database_url)
    db.migrate()
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    dataset = import_paths(db, "stdio-fixture", [empty])
    environment = {
        "DATAKEEL_DATABASE_URL": database_url,
        "DATAKEEL_HOME": str(home),
        **dict.fromkeys(("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"), ""),
        **dict.fromkeys(("http_proxy", "https_proxy", "all_proxy"), ""),
    }
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "datakeel.cli", "mcp"],
        env=environment,
        keep_alive=False,
        log_file=tmp_path / "stdio.log",
    )

    async def scenario() -> None:
        async with Client(
            transport,
            mode="legacy",
            client_info=Implementation(name="protocol-fixture", version="1"),
        ) as client:
            await _exercise(client, db, dataset.id)

    try:
        asyncio.run(scenario())
        _assert_audit(db)
    finally:
        db.engine.dispose()


def _local_http_client(
    headers: dict[str, str] | None = None,
    timeout: httpx2.Timeout | None = None,
    auth: httpx2.Auth | None = None,
) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(headers=headers, timeout=timeout, auth=auth, trust_env=False)


class ReadyServer(uvicorn.Server):
    """Signal completed socket startup without timing assumptions or polling."""

    def __init__(self, config: uvicorn.Config) -> None:
        """Attach a readiness event to the local test server."""
        super().__init__(config)
        self.ready = asyncio.Event()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Notify the client only after the prebound listener is accepting requests."""
        await super().startup(sockets)
        self.ready.set()


def test_sse_when_loopback_client_connects_controls_and_audits_real_calls(
    db: Database, dataset: DatasetView
) -> None:
    """Handshake across an actual loopback socket and verify the shared database audit."""
    app = create_server(db).http_app(transport="sse", path="/sse")
    server = ReadyServer(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))

    async def scenario(listener: socket.socket) -> None:
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            await asyncio.wait_for(server.ready.wait(), timeout=5)
            transport = SSETransport(
                f"http://127.0.0.1:{listener.getsockname()[1]}/sse",
                httpx_client_factory=_local_http_client,
            )
            async with Client(
                transport,
                mode="legacy",
                client_info=Implementation(name="protocol-fixture", version="1"),
            ) as client:
                await _exercise(client, db, dataset.id)
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        asyncio.run(scenario(listener))
    _assert_audit(db)
