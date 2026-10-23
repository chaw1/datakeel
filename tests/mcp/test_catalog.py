# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A real MCP handshake exposes catalog functions and audits their actual asset reads."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client

from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.tool_invocations import list_invocations
from tests.enterprise_support import enterprise_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_mcp_when_catalog_tools_called_records_nonempty_asset_refs(
    db: Database, tmp_path: Path
) -> None:
    """All four functions are discoverable and callable through the production dispatcher."""
    enterprise_fixture(db, tmp_path / "enterprise")

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            listed = {tool.name for tool in await client.list_tools()}
            assert {"ask_data", "list_metrics", "explain_metric", "impact_of"} <= listed
            calls = (
                (
                    "ask_data",
                    JsonDocument(
                        {
                            "question": "上个季度华东区零售额是多少",
                            "reference_instant": "2026-10-01T00:00:00Z",
                        }
                    ),
                ),
                ("list_metrics", JsonDocument({"limit": 2})),
                ("explain_metric", JsonDocument({"metric_id": "retail_revenue"})),
                ("impact_of", JsonDocument({"asset_id": "ecommerce/main/orders/paid_amount"})),
            )
            for name, arguments in calls:
                response = await client.call_tool(name, arguments.root)
                outcome = ToolOutcome.model_validate(response.structured_content)
                assert outcome.status == "SUCCEEDED"
                assert outcome.asset_refs

    asyncio.run(scenario())
    invocations = list_invocations(db)
    assert len(invocations) == 4
    assert all(item.asset_refs for item in invocations)
