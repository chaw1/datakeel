# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""MCP schemas, prepare-only semantics, and rejected calls share the domain audit path."""

import asyncio
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client, Context
from jsonschema import Draft202012Validator
from mcp_types import Implementation

from datakeel.actions.service import list_runs
from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.mcp.catalog import tool_definitions
from datakeel.mcp.dispatch import caller_context
from datakeel.ontology import tooling
from datakeel.ontology.models import ObjectSet
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.object_queries import evaluate
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.views import DatasetView

if TYPE_CHECKING:
    from pydantic import JsonValue


async def call(client: Client, name: str, arguments: JsonDocument) -> ToolOutcome:
    """Decode the structured result even for declared tool failures."""
    response = await client.call_tool(name, arguments.root, raise_on_error=False)
    result = ToolOutcome.model_validate(response.structured_content)
    assert response.is_error == (result.status == "FAILED")
    return result


def test_server_when_initialized_lists_registered_valid_model_generated_tools(db: Database) -> None:
    """Expose exact argument contracts and structured outcomes through a real MCP handshake."""

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            assert client.initialize_result is not None
            assert client.initialize_result.server_info.name == "Datakeel"
            listed = await client.list_tools()
        expected = {item.name: item for item in tool_definitions()}
        assert len(listed) == len(expected) == 34
        assert {"annotation_quality", "annotation_acceptance"} <= set(expected)
        assert {"query_kg", "explain_relation", "run_kg_extraction"} <= set(expected)
        for tool in listed:
            Draft202012Validator.check_schema(tool.input_schema)
            assert tool.output_schema is not None
            Draft202012Validator.check_schema(tool.output_schema)
            assert tool.input_schema["title"] == expected[tool.name].parameters.root["title"]
            assert tool.input_schema["additionalProperties"] is False
            assert tool.annotations is not None
            assert tool.annotations.open_world_hint is False
        assert list_invocations(db) == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "action",
    [
        "quarantine_files",
        "unquarantine_files",
        "create_version_from_selection",
        "run_pipeline",
        "save_metadata",
        "delete_files",
        "export_dataset",
    ],
)
def test_action_when_called_only_prepares_an_attributed_plan(
    db: Database, dataset: DatasetView, action: str
) -> None:
    """All seven tools expose real plans while leaving execution to the explicit control."""
    params: dict[str, JsonValue] = {"selection": {"dataset_id": dataset.id}}
    if action in {"run_pipeline", "save_metadata", "export_dataset"}:
        params = {"dataset_id": dataset.id}
    if action == "save_metadata":
        params.update({"values": {"name": "Proposed name"}, "reason": "Fixture decision"})

    async def scenario() -> ToolOutcome:
        async with Client(
            create_server(db),
            mode="legacy",
            client_info=Implementation(name="fixture-client", version="1"),
        ) as client:
            return await call(client, action, JsonDocument(params))

    result = asyncio.run(scenario())
    assert result.status == "SUCCEEDED"
    assert result.plan is not None
    assert result.plan.action_type == action
    assert result.plan.status == "PREPARED"
    assert result.plan.agent_id == "fixture-client"
    assert result.plan.session_id
    assert result.requires_approval == (action in {"delete_files", "export_dataset"})
    assert result.asset_refs
    assert list_runs(db) == []
    assert len(evaluate(db, ObjectSet(dataset_id=dataset.id)).objects) == 2
    invocation = list_invocations(db)[0]
    assert invocation.actor == "local"
    assert invocation.agent_id == result.plan.agent_id
    assert invocation.session_id == result.plan.session_id


@pytest.mark.parametrize(
    ("name", "arguments"),
    [("unknown", {}), ("get_quality", {"extra": 1}), ("list_datasets", {"limit": 0})],
)
def test_tool_when_name_or_schema_invalid_records_failure_before_responding(
    db: Database, name: str, arguments: dict[str, int]
) -> None:
    """Protocol validation cannot hide rejected requests from durable invocation history."""

    async def scenario() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            return await call(client, name, JsonDocument(arguments))

    outcome = asyncio.run(scenario())
    assert outcome.status == "FAILED"
    assert outcome.error
    invocation = list_invocations(db)[0]
    assert invocation.id == outcome.invocation_id
    assert invocation.name == name
    assert invocation.status == "FAILED"
    assert invocation.session_id
    assert invocation.arguments_digest
    assert invocation.argument_keys == sorted(arguments)
    assert invocation.completed_at is not None


def test_tool_when_unexpected_failure_occurs_retains_audit_and_protocol_error(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected domain failures are rethrown after audit instead of becoming success."""

    def fail(*_args: object, **_kwargs: object) -> ToolOutcome:
        msg = "fixture storage failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(tooling, "invoke_function", fail)

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool("list_datasets", {}, raise_on_error=False)
            assert response.is_error

    asyncio.run(scenario())
    assert list_invocations(db)[0].status == "FAILED"
    assert "fixture storage failure" in (list_invocations(db)[0].error or "")


def test_caller_when_no_protocol_session_is_available_uses_local_attribution(db: Database) -> None:
    """Allow direct SDK administration without inventing a client or session identity."""

    async def scenario() -> None:
        async with Context(fastmcp=create_server(db)) as context:
            caller = caller_context(context)
            assert caller.actor == "local"
            assert caller.agent_id == "mcp"
            assert caller.session_id is None

    asyncio.run(scenario())
