# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Traverse every native entry against the same persistent authorization policy."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import (
    AccessEntry,
    AccessScope,
    AssetClassification,
    AssetUsageQuery,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from tests.assets.entry_helpers import (
    EntryResources,
    GrantState,
    grant,
    publish,
    revoke,
    seed_resources,
)

ENTRIES: tuple[tuple[AccessEntry, AccessScope], ...] = (
    ("ask", "query"),
    ("export", "export"),
    ("download", "download"),
    ("mcp", "query"),
    ("agent", "query"),
)


def _http(db: Database, resources: EntryResources, entry: AccessEntry) -> bool:
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        if entry == "ask":
            response = client.post(
                "/api/ask",
                json={
                    "question": "上个季度华东区零售额是多少",
                    "actor": "local",
                    "reference_instant": "2026-10-01T00:00:00Z",
                },
            )
        elif entry == "export":
            response = client.get(
                "/api/export",
                params={
                    "format": "croissant",
                    "dataset_id": resources.dataset_id,
                },
            )
        else:
            response = client.get(
                f"/api/datasets/{resources.dataset_id}/files/{resources.file_id}/download"
            )
    assert response.status_code in {200, 403}, response.text
    if response.status_code == 403:
        assert "apply for access" in response.text
        assert "4979475" not in response.text
        assert "Generated asset access sample" not in response.text
    return response.status_code == 200


def _tool(db: Database, resources: EntryResources, entry: AccessEntry) -> bool:
    arguments = JsonDocument({"dataset_id": resources.dataset_id})
    if entry == "mcp":

        async def call() -> ToolOutcome:
            async with Client(create_server(db), mode="legacy") as client:
                response = await client.call_tool(
                    "search_files", arguments.root, raise_on_error=False
                )
                return ToolOutcome.model_validate(response.structured_content)

        outcome = asyncio.run(call())
    else:
        outcome = invoke_tool(db, "search_files", arguments, ToolCallContext())
    if outcome.status == "FAILED":
        assert "apply for access" in (outcome.error or "")
        assert outcome.content.root == {}
    return outcome.status == "SUCCEEDED"


@pytest.mark.parametrize("classification", ["request", "restricted"])
@pytest.mark.parametrize("state", ["none", "expired", "revoked", "wrong_scope", "valid"])
def test_all_native_entries_enforce_persistent_grants(
    db: Database, tmp_path: Path, classification: AssetClassification, state: GrantState
) -> None:
    """Every entry denies missing/expired/revoked/wrong scopes and allows an active exact grant."""
    resources = seed_resources(db, tmp_path)
    dataset_asset = publish(db, AssetRef(asset_id=resources.dataset_id), classification)
    metric_asset = publish(
        db, AssetRef(asset_type="metric", asset_id="retail_revenue"), classification
    )
    for entry, scope in ENTRIES:
        asset = metric_asset if entry == "ask" else dataset_asset
        grant_id = grant(db, asset, state, scope)
        allowed = (
            _http(db, resources, entry)
            if entry in {"ask", "export", "download"}
            else _tool(db, resources, entry)
        )
        assert allowed == (state == "valid"), (classification, state, entry)
        if grant_id and state != "revoked":
            revoke(db, grant_id)
    usages = list_usage(db, AssetUsageQuery(actor="local"))
    assert {item.entry for item in usages} == (
        {entry for entry, _ in ENTRIES} if state == "valid" else set()
    )
    assert len(usages) == (5 if state == "valid" else 0)
    assert all(item.grant_id for item in usages)
