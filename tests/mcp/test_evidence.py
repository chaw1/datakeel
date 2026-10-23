# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real MCP evidence calls retain validated schemas and durable asset attribution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.tool_invocations import list_invocations
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_mcp_when_evidence_tools_called_returns_provenance_and_records_asset_refs(
    db: Database, tmp_path: Path
) -> None:
    """All three new reads work through a real protocol session with nonempty audit refs."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    version, files = source_manifest(db, dataset)
    asset_id = files[0].id

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            listed = {tool.name: tool for tool in await client.list_tools()}
            for name in ("query_evidence", "get_evidence", "explain_sample"):
                definition = listed[name]
                assert definition.annotations is not None
                assert definition.annotations.read_only_hint is True
                if name == "query_evidence":
                    properties = definition.input_schema["properties"]
                    assert properties["object_type"]["enum"] == ["file"]
                arguments = (
                    JsonDocument({"dataset_id": dataset, "page_size": 2})
                    if name == "query_evidence"
                    else JsonDocument({"asset_id": asset_id})
                )
                response = await client.call_tool(name, arguments.root, raise_on_error=False)
                result = ToolOutcome.model_validate(response.structured_content)
                assert not response.is_error
                assert result.status == "SUCCEEDED", result.error
                assert result.asset_refs
                assert any(ref.version == version for ref in result.asset_refs)
                assert result.content.root["function"] == name

    asyncio.run(scenario())
    invocations = list_invocations(db)
    assert len(invocations) == 3
    assert {item.name for item in invocations} == {
        "query_evidence",
        "get_evidence",
        "explain_sample",
    }
    assert all(
        item.asset_refs and item.actor == "local" and item.session_id and item.completed_at
        for item in invocations
    )


def test_mcp_when_evidence_arguments_invalid_still_audits_requested_file(db: Database) -> None:
    """Schema rejection cannot hide a requested sample or accept fabricated actor authority."""

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(
                "get_evidence",
                {"asset_id": "missing-file", "actor": "admin"},
                raise_on_error=False,
            )
            result = ToolOutcome.model_validate(response.structured_content)
            assert response.is_error
            assert result.status == "FAILED"
            assert any(
                ref.asset_type == "file" and ref.asset_id == "missing-file"
                for ref in result.asset_refs
            )

    asyncio.run(scenario())
    invocation = list_invocations(db)[0]
    assert invocation.status == "FAILED"
    assert invocation.asset_refs
    assert invocation.actor == "local"


@pytest.mark.parametrize("name", ["query_evidence", "quarantine_files"])
def test_mcp_when_version_scoped_request_rejected_retains_requested_versions(
    db: Database, name: str
) -> None:
    """Validation failures retain explicit version assets before a selection can run."""

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            selection = {"version_ids": ["version-target"], "limit": 0}
            arguments = selection if name == "query_evidence" else {"selection": selection}
            response = await client.call_tool(name, arguments, raise_on_error=False)
            result = ToolOutcome.model_validate(response.structured_content)
            assert response.is_error
            assert result.status == "FAILED"
            assert any(
                ref.asset_type == "version"
                and ref.asset_id == "version-target"
                and ref.version == "version-target"
                for ref in result.asset_refs
            )

    asyncio.run(scenario())
    invocation = list_invocations(db)[0]
    assert invocation.status == "FAILED"
    assert invocation.asset_refs[0].asset_id == "version-target"
