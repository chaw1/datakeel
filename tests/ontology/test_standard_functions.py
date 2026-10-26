# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standards tools read confirmed coverage and usage through the shared audited registry."""

from pathlib import Path

import pytest

from datakeel.agent.tools import deferred_tools, resident_tools
from datakeel.core.models import JsonDocument
from datakeel.core.standard_models import CoverageGroup, StandardsCoverage
from datakeel.harness.standard_cases import seed_standard_demo
from datakeel.mcp.catalog import tool_definitions
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import list_invocations


def test_standard_tools_are_deferred_and_shared_with_mcp() -> None:
    """Discovery describes business questions while preserving the resident tool budget."""
    names = {"query_standard_coverage", "list_standard_usage"}
    assert not names.intersection(item.name for item in resident_tools())
    assert names <= {item.name for item in deferred_tools()}
    assert names <= {item.name for item in tool_definitions()}
    assert all("标准" in item.description for item in deferred_tools() if item.name in names)


@pytest.mark.parametrize("standard", ["customer_id", "客户编号", "customer id"])
def test_usage_resolves_bilingual_names_and_returns_real_column_refs(
    db: Database, tmp_path: Path, standard: str
) -> None:
    """Only confirmed associations count; candidates and raw rows are excluded."""
    seed_standard_demo(db, tmp_path / "sources")
    result = invoke_tool(
        db, "list_standard_usage", JsonDocument({"standard": standard}), ToolCallContext()
    )
    assert result.status == "SUCCEEDED"
    assert len(result.asset_refs) == 2
    assert all(ref.asset_type == "column" for ref in result.asset_refs)
    assert JsonDocument.model_validate(result.content.root["data"]).root["total"] == 2
    assert len(list_invocations(db)) == 1
    assert "values" not in result.content.model_dump_json()


def test_coverage_ranks_dirty_table_and_scopes_reads_without_changing_state(
    db: Database, tmp_path: Path
) -> None:
    """A clean table outranks the dirty comparison using the actual check population."""
    seed_standard_demo(db, tmp_path / "sources")
    result = invoke_function(db, "query_standard_coverage", JsonDocument({"limit": 1}))
    payload = JsonDocument.model_validate(result.data)
    worst = payload.root["worst_tables"]
    assert isinstance(worst, list)
    assert CoverageGroup.model_validate(worst[0]).key == "standards_demo/main/dirty_customers"
    clean = invoke_function(
        db,
        "query_standard_coverage",
        JsonDocument({"table_id": "standards_demo/main/clean_customers"}),
    )
    clean_coverage = StandardsCoverage.model_validate(
        JsonDocument.model_validate(clean.data).root["coverage"]
    )
    assert clean_coverage.overall.compliance == 1
    absent = invoke_function(db, "list_standard_usage", JsonDocument({"standard": "missing"}))
    assert not absent.asset_refs
    assert JsonDocument.model_validate(absent.data).root["total"] == 0
