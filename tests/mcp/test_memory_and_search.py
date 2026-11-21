# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local MCP discovery and memory preserve privacy, provenance and durable audit."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator
from mcp_types import Implementation, TextContent, TextResourceContents
from pydantic import TypeAdapter

from datakeel.core.agent_models import ConversationCreate, ToolDefinition
from datakeel.core.memory_models import MemoryCreate, MemoryEntry
from datakeel.core.models import JsonDocument
from datakeel.dataset_store.dataset_service import DatasetInput, create_dataset
from datakeel.delegation.loader import list_agents
from datakeel.delegation.models import AgentDefinition
from datakeel.mcp import create_server, local_tools
from datakeel.mcp.catalog import tool_definitions
from datakeel.mcp.server import OUTPUT_SCHEMA
from datakeel.memory.service import create_memory, get_memory, reinforce_memories
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.conversation_store import create
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.datasets.views import DatasetView
    from datakeel.storage.database import Database


async def _call(client: Client, name: str, arguments: JsonDocument) -> ToolOutcome:
    response = await client.call_tool(name, arguments.root, raise_on_error=False)
    Draft202012Validator(OUTPUT_SCHEMA).validate(response.structured_content)
    outcome = ToolOutcome.model_validate(response.structured_content)
    assert response.is_error == (outcome.status == "FAILED")
    assert len(response.content) == 1
    assert isinstance(response.content[0], TextContent)
    assert ToolOutcome.model_validate_json(response.content[0].text) == outcome
    return outcome


def _assert_audit(db: Database, outcomes: list[ToolOutcome]) -> None:
    invocations = list_invocations(db)
    assert len(invocations) == len(outcomes)
    for invocation, outcome in zip(invocations, outcomes, strict=True):
        assert invocation.id == outcome.invocation_id
        assert invocation.name == outcome.name
        assert invocation.status == outcome.status
        assert invocation.error == outcome.error
        assert invocation.actor == "local"
        assert invocation.session_id
        assert invocation.arguments_digest
        assert invocation.completed_at is not None
        assert invocation.elapsed_ms >= 0


@pytest.mark.parametrize("query", ["数据集 质量", "dataset quality"])
def test_tool_search_ranks_bilingual_queries_and_bounds_full_schemas(
    db: Database, query: str
) -> None:
    """Both languages rank useful matches and return only the top eight complete schemas."""

    async def scenario() -> list[ToolOutcome]:
        async with Client(create_server(db), mode="legacy") as client:
            outcome = await _call(client, "tool_search", JsonDocument({"query": query}))
            assert outcome.status == "SUCCEEDED"
            tools = TypeAdapter(list[ToolDefinition]).validate_python(outcome.content.root["tools"])
            assert len(tools) == 8
            assert tools[0].name == "get_quality"
            assert outcome.content.root["truncated"] is True
            assert outcome.content.root["total_matches"] > len(tools)
            expected = {tool.name: tool for tool in tool_definitions()}
            assert all(tool == expected[tool.name] for tool in tools)
            for tool in tools:
                Draft202012Validator.check_schema(tool.parameters.root)
            return [outcome]

    _assert_audit(db, asyncio.run(scenario()))


@pytest.mark.parametrize(
    "name", ["tool_search", "search_memories", "write_memory", "update_memory"]
)
def test_tool_search_includes_local_tools_in_full_catalog(db: Database, name: str) -> None:
    """Local capabilities are discoverable by exact identifier alongside domain tools."""

    async def scenario() -> list[ToolOutcome]:
        async with Client(create_server(db), mode="legacy") as client:
            outcome = await _call(client, "tool_search", JsonDocument({"query": name}))
            tools = TypeAdapter(list[ToolDefinition]).validate_python(outcome.content.root["tools"])
            assert [tool.name for tool in tools] == [name]
            assert outcome.content.root["total_matches"] == 1
            assert outcome.content.root["truncated"] is False
            return [outcome]

    _assert_audit(db, asyncio.run(scenario()))


async def _memory_resource(client: Client) -> list[MemoryEntry]:
    contents = await client.read_resource("datakeel://memories")
    assert len(contents) == 1
    assert isinstance(contents[0], TextResourceContents)
    return TypeAdapter(list[MemoryEntry]).validate_json(contents[0].text)


async def _search_written_memory(
    client: Client, memory: MemoryEntry, outcomes: list[ToolOutcome]
) -> None:
    for arguments in (
        {"query": "wave7b_token"},
        {"query": "质量规则"},
        {"dataset_id": memory.dataset_id, "limit": 1},
    ):
        outcome = await _call(client, "search_memories", JsonDocument.model_validate(arguments))
        outcomes.append(outcome)
        assert outcome.status == "SUCCEEDED"
        assert outcome.content.root["count"] == 1
        entries = TypeAdapter(list[MemoryEntry]).validate_python(outcome.content.root["memories"])
        assert [entry.id for entry in entries] == [memory.id]
        assert entries[0].content == memory.content


async def _update_written_memory(
    client: Client, memory: MemoryEntry, outcomes: list[ToolOutcome]
) -> None:
    updated = await _call(
        client,
        "update_memory",
        JsonDocument({"memory_id": memory.id, "content": "质量规则 v2 editor@example.org"}),
    )
    outcomes.append(updated)
    assert updated.status == "SUCCEEDED"
    assert updated.content.root["memory_id"] == memory.id
    assert updated.content.root["dataset_id"] == memory.dataset_id
    assert updated.content.root["content"] == "质量规则 v2 [REDACTED]"
    assert datetime.fromisoformat(str(updated.content.root["updated_at"])).tzinfo is not None
    entries = await _memory_resource(client)
    assert len(entries) == 1
    assert entries[0].content == updated.content.root["content"]
    assert entries[0].model_dump(exclude={"content", "current_strength"}) == memory.model_dump(
        exclude={"content", "current_strength"}
    )
    missing = await _call(
        client, "update_memory", JsonDocument({"memory_id": "missing", "content": "replacement"})
    )
    outcomes.append(missing)
    assert missing.status == "FAILED"
    assert "Memory not found" in (missing.error or "")


def test_memory_lifecycle_redacts_content_and_resources_reflect_each_change(
    db: Database, dataset: DatasetView
) -> None:
    """Write, bilingual search and update operate through MCP with one audit row per call."""

    async def scenario() -> list[ToolOutcome]:
        async with Client(
            create_server(db),
            mode="legacy",
            client_info=Implementation(name="memory-fixture", version="1"),
        ) as client:
            assert await _memory_resource(client) == []
            written = await _call(
                client,
                "write_memory",
                JsonDocument(
                    {
                        "content": "wave7b_token 质量规则 owner@example.org +1 (415) 555-0123",
                        "dataset_id": dataset.id,
                    }
                ),
            )
            assert written.status == "SUCCEEDED"
            outcomes = [written]
            entries = await _memory_resource(client)
            assert len(entries) == 1
            memory = entries[0]
            assert memory.id == written.content.root["memory_id"]
            assert memory.content == "wave7b_token 质量规则 [REDACTED] [REDACTED]"
            assert memory.dataset_id == dataset.id
            await _search_written_memory(client, memory, outcomes)
            await _update_written_memory(client, memory, outcomes)
            return outcomes

    _assert_audit(db, asyncio.run(scenario()))
    assert all(item.agent_id == "memory-fixture" for item in list_invocations(db))


def test_update_preserves_existing_conversation_provenance_and_strength(
    db: Database, dataset: DatasetView
) -> None:
    """Editing a sourced, reinforced memory does not erase its scope or strengthen it."""
    conversation = create(db, ConversationCreate())
    original = create_memory(
        db,
        MemoryCreate(
            content="Existing quality policy",
            dataset_id=dataset.id,
            source_conversation_id=conversation.id,
        ),
    )
    reinforce_memories(db, [original.id])
    before = get_memory(db, original.id)
    assert before.strength > original.strength
    assert before.source_conversation_ids == [conversation.id]

    async def scenario() -> list[ToolOutcome]:
        outcomes: list[ToolOutcome] = []
        async with Client(create_server(db), mode="legacy") as client:
            await _update_written_memory(client, before, outcomes)
        return outcomes

    _assert_audit(db, asyncio.run(scenario()))


def test_memory_search_applies_dataset_scope_and_result_limit(
    db: Database, dataset: DatasetView
) -> None:
    """Search excludes another dataset's memory and limits the filtered matches."""
    other = create_dataset(db, DatasetInput(name="Other memory scope"))
    expected = {
        create_memory(db, MemoryCreate(content=content, dataset_id=dataset.id)).id
        for content in ("quality alpha", "quality beta")
    }
    create_memory(db, MemoryCreate(content="quality gamma", dataset_id=other.id))

    async def scenario() -> list[ToolOutcome]:
        outcomes: list[ToolOutcome] = []
        async with Client(create_server(db), mode="legacy") as client:
            for limit in (20, 1):
                outcome = await _call(
                    client,
                    "search_memories",
                    JsonDocument({"query": "quality", "dataset_id": dataset.id, "limit": limit}),
                )
                outcomes.append(outcome)
                entries = TypeAdapter(list[MemoryEntry]).validate_python(
                    outcome.content.root["memories"]
                )
                assert outcome.content.root["count"] == len(entries) == min(2, limit)
                assert {entry.id for entry in entries} <= expected
        return outcomes

    _assert_audit(db, asyncio.run(scenario()))


def test_resources_list_all_six_bundled_specialists(db: Database) -> None:
    """Resource discovery and reads expose the validated bundled specialist contracts."""

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            resources = await client.list_resources()
            assert {"datakeel://agents", "datakeel://memories"} <= {
                str(resource.uri) for resource in resources
            }
            contents = await client.read_resource("datakeel://agents")
            assert len(contents) == 1
            assert isinstance(contents[0], TextResourceContents)
            agents = TypeAdapter(list[AgentDefinition]).validate_json(contents[0].text)
            assert len(agents) == 6
            assert agents == list_agents()

    asyncio.run(scenario())
    assert list_invocations(db) == []


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("tool_search", {"query": "dataset", "limit": 0}),
        ("search_memories", {"limit": 101}),
        ("search_memories", {"unexpected": True}),
        ("write_memory", {"content": " "}),
        ("write_memory", {"content": "policy", "dataset_id": "missing"}),
        ("update_memory", {"memory_id": "memory", "content": " "}),
        ("update_memory", {"memory_id": "", "content": "policy"}),
    ],
)
def test_local_tools_audit_validation_and_domain_failures(
    db: Database, name: str, arguments: dict[str, str | int | bool]
) -> None:
    """Rejected local calls retain the same structured error and audit contract as domain tools."""

    async def scenario() -> list[ToolOutcome]:
        async with Client(create_server(db), mode="legacy") as client:
            outcome = await _call(client, name, JsonDocument.model_validate(arguments))
            assert outcome.status == "FAILED"
            assert outcome.error
            return [outcome]

    _assert_audit(db, asyncio.run(scenario()))
    assert list_invocations(db)[0].argument_keys == sorted(arguments)


def test_local_tool_unexpected_failure_is_audited_before_protocol_error(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected implementation errors retain a completed failed invocation."""

    def fail(*_args: object, **_kwargs: object) -> JsonDocument:
        msg = "fixture search failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(local_tools, "search_tools", fail)

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(
                "tool_search", {"query": "dataset"}, raise_on_error=False
            )
            assert response.is_error

    asyncio.run(scenario())
    invocations = list_invocations(db)
    assert len(invocations) == 1
    assert invocations[0].status == "FAILED"
    assert invocations[0].completed_at is not None
    assert invocations[0].elapsed_ms >= 0
    assert "fixture search failure" in (invocations[0].error or "")
