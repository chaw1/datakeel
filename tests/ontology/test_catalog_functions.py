# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata and ask functions share typed parameters and retain audit asset identities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.tools import deferred_tools, resident_tools
from datakeel.core.ask_models import AskAnswer
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.ask_store import get_answer
from datakeel.storage.tool_invocations import list_invocations
from tests.enterprise_support import enterprise_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_catalog_functions_when_registered_are_discoverable_and_model_sql_is_absent() -> None:
    """Expose the four domain functions without a freeform SQL-generation parameter."""
    tools = {item.name: item for item in deferred_tools()}
    assert not {"ask_data", "list_metrics", "explain_metric", "impact_of"}.intersection(
        item.name for item in resident_tools()
    )
    assert {"ask_data", "list_metrics", "explain_metric", "impact_of"} <= tools.keys()
    properties = tools["ask_data"].parameters.root["properties"]
    assert isinstance(properties, dict)
    assert "sql" not in properties
    assert "provider" not in properties


def test_list_metrics_when_empty_or_filter_misses_returns_empty_refs(
    db: Database, tmp_path: Path
) -> None:
    """Listing no metric is valid and never invents an addressed asset."""
    empty = invoke_function(db, "list_metrics", JsonDocument({}))
    assert empty.asset_refs == []
    enterprise_fixture(db, tmp_path / "enterprise")
    for arguments in ({"search": "absent"}, {"status": "unresolved"}, {"offset": 99}):
        assert not invoke_function(
            db, "list_metrics", JsonDocument.model_validate(arguments)
        ).asset_refs
    result = invoke_function(
        db, "list_metrics", JsonDocument({"search": "retail", "status": "resolved", "limit": 1})
    )
    assert len(result.asset_refs) == 1
    assert result.asset_refs[0].asset_type == "metric"


def test_catalog_functions_when_reading_assets_audit_actual_references(
    db: Database, tmp_path: Path
) -> None:
    """Catalog calls use durable invocation traces with real metric or field references."""
    enterprise_fixture(db, tmp_path / "enterprise")
    for name, arguments in (
        ("explain_metric", JsonDocument({"metric_id": "retail_revenue"})),
        ("impact_of", JsonDocument({"asset_id": "ecommerce/main/orders/paid_amount"})),
    ):
        result = invoke_tool(db, name, arguments, ToolCallContext())
        assert result.status == "SUCCEEDED"
        assert result.asset_refs
        assert not any(ref.asset_type == "dataset" for ref in result.asset_refs)
    assert all(item.asset_refs for item in list_invocations(db))


def test_ask_function_preserves_saved_answers_and_explicit_null_state_fields(
    db: Database, tmp_path: Path
) -> None:
    """All answer states round-trip; unresolved tool results explicitly exclude numeric data."""
    enterprise_fixture(db, tmp_path / "enterprise")
    for question in ("上个季度华东区零售额是多少", "退货率为什么上升", "上个季度营业额是多少"):
        result = invoke_function(
            db,
            "ask_data",
            JsonDocument({"question": question, "reference_instant": "2026-10-01T00:00:00Z"}),
        )
        answer = AskAnswer.model_validate(result.data)
        assert answer == get_answer(db, answer.id)
        assert answer.recognition is not None
        assert any(
            ref.asset_type == "question" and ref.asset_id == answer.id for ref in result.asset_refs
        )
        if answer.status == "answered":
            assert {"metric", "table", "column"} <= {ref.asset_type for ref in result.asset_refs}
        else:
            assert {ref.asset_type for ref in result.asset_refs} == {"question"}
            assert isinstance(result.data, dict)
            assert all(key in result.data for key in ("metric_card", "sql", "result"))
            assert all(result.data[key] is None for key in ("metric_card", "sql", "result"))
