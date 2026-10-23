# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""README verification exercises real metadata tools in a strictly local environment."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client

from datakeel.mcp import create_server
from datakeel.storage.tool_invocations import list_invocations
from scripts.check_readme import local_environment, verify_enterprise_stdio
from tests.enterprise_support import enterprise_fixture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_readme_enterprise_checks_measure_four_actual_audited_tools(
    db: Database, tmp_path: Path
) -> None:
    """The README checker validates generated facts through the production MCP dispatcher."""
    enterprise_fixture(db, tmp_path / "enterprise")

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            await verify_enterprise_stdio(client)

    asyncio.run(scenario())
    invocations = list_invocations(db)
    assert {item.name for item in invocations} == {
        "ask_data",
        "list_metrics",
        "explain_metric",
        "impact_of",
    }
    assert len(invocations) == 4
    assert all(item.status == "SUCCEEDED" and item.asset_refs for item in invocations)


def test_readme_commands_discard_inherited_service_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command checker never reuses inherited cloud, database, or model destinations."""
    for name in (
        "DATAKEEL_DATABASE_URL",
        "DATAKEEL_S3_ENDPOINT",
        "DATAKEEL_LLM_URL",
        "DATAKEEL_TEST_DATABASE_URL",
        "AWS_ACCESS_KEY_ID",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.setenv(name, "synthetic-external-setting")
    environment = local_environment(tmp_path)
    assert environment["DATAKEEL_HOME"] == str(tmp_path)
    assert environment["DATAKEEL_DATABASE_URL"] == f"sqlite:///{tmp_path / 'state.db'}"
    assert "DATAKEEL_S3_ENDPOINT" not in environment
    assert "DATAKEEL_TEST_DATABASE_URL" not in environment
    assert not any(key.startswith(("AWS_", "OPENAI_", "ANTHROPIC_")) for key in environment)
