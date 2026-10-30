# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tool discovery cannot grant hidden approval or execution capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.tools import ToolCatalog, deferred_tools, resident_tools
from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    ToolCall,
    ToolDefinition,
)
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_history import DEFERRED_READ_FUNCTIONS
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_catalog_when_constructed_has_only_read_tools_and_deferred_actions() -> None:
    """Never expose approve_plan or execute_plan through either discovery list."""
    assert len(resident_tools()) == 10
    assert len(deferred_tools()) == 92 + 1  # TAILS-4: T3 assignees
    assert {"training_distribution", "training_leakage"} <= {tool.name for tool in deferred_tools()}
    training = next(tool for tool in deferred_tools() if tool.name == "get_training_quality")
    assert "clean_training_data" in {tool.name for tool in deferred_tools()}
    assert training.name in PARAMETER_MODELS
    assert training.name in DEFERRED_READ_FUNCTIONS
    assert training.parameters.root["required"] == ["dataset_id"]
    properties = training.parameters.root["properties"]
    assert isinstance(properties, dict)
    assert "version_id" in properties
    assert "submit_custom_operator" in {tool.name for tool in deferred_tools()}
    assert "publish_release" in {tool.name for tool in deferred_tools()}
    assert "confirm_metric_draft" in {tool.name for tool in deferred_tools()}
    assert {"annotation_quality", "annotation_acceptance"} <= {
        tool.name for tool in deferred_tools()
    }
    assert not {"approve_plan", "execute_plan"}.intersection(
        tool.name for tool in resident_tools() + deferred_tools()
    )


def test_catalog_when_discovered_persists_schemas_and_recovers_them_from_memory(
    db: Database,
) -> None:
    """Reload only registered action names from a complete persisted tool-search result."""
    conversation = Conversation(id="session", config=ConversationCreate())
    catalog = ToolCatalog(conversation)
    call = ToolCall(name="tool_search", arguments=JsonDocument({"query": "quarantine"}))
    result = catalog.invoke(db, call, ToolCallContext(session_id=conversation.id))
    assert set(catalog.loaded) == {"quarantine_files", "unquarantine_files"}
    conversation = conversation.model_copy(
        update={
            "messages": [
                ChatMessage(role="tool", name="tool_search", content=result.model_dump_json())
            ]
        }
    )
    assert ToolCatalog(conversation).loaded == catalog.loaded
    assert list_invocations(db)[0].name == "tool_search"


def test_catalog_when_unknown_or_hidden_call_requested_records_failed_attempt(db: Database) -> None:
    """Reject invented calls even when a malicious provider bypasses advertised schemas."""
    catalog = ToolCatalog(Conversation(id="session", config=ConversationCreate()))
    for name in ("approve_plan", "execute_plan", "quarantine_files", "unknown"):
        result = catalog.invoke(db, ToolCall(name=name), ToolCallContext())
        assert result.status == "FAILED"
    assert len(list_invocations(db)) == 4


def test_catalog_when_search_invalid_returns_validation_evidence(db: Database) -> None:
    """Keep malformed discovery requests inside the same failed-tool protocol."""
    catalog = ToolCatalog(Conversation(id="session", config=ConversationCreate()))
    result = catalog.invoke(db, ToolCall(name="tool_search"), ToolCallContext())
    assert result.status == "FAILED"
    assert "query" in (result.error or "")


def test_catalog_when_new_read_requested_requires_discovery_and_restores_it(db: Database) -> None:
    """A deferred read becomes callable only after a recorded search and survives replay."""
    conversation = Conversation(id="catalog-session", config=ConversationCreate())
    catalog = ToolCatalog(conversation)
    denied = catalog.invoke(db, ToolCall(name="list_metrics"), ToolCallContext())
    assert denied.status == "FAILED"
    search = catalog.invoke(
        db,
        ToolCall(name="tool_search", arguments=JsonDocument({"query": "list_metrics"})),
        ToolCallContext(),
    )
    assert set(catalog.loaded) == {"list_metrics"}
    restored = ToolCatalog(
        conversation.model_copy(
            update={
                "messages": [
                    ChatMessage(role="tool", name="tool_search", content=search.model_dump_json())
                ]
            }
        )
    )
    assert restored.loaded == catalog.loaded
    result = restored.invoke(db, ToolCall(name="list_metrics"), ToolCallContext())
    assert result.status == "SUCCEEDED"
    assert result.asset_refs == []


def test_catalog_when_all_new_reads_discovered_never_loads_execution_authority(
    db: Database,
) -> None:
    """Discovery includes catalog and graph reads while controls remain unavailable."""
    catalog = ToolCatalog(Conversation(id="catalog-session", config=ConversationCreate()))
    for name in (
        "ask_data",
        "list_metrics",
        "explain_metric",
        "impact_of",
        "query_kg",
        "explain_relation",
        "query_standard_coverage",
        "list_standard_usage",
        "list_quality_rules",
        "get_table_quality",
        "get_training_quality",
    ):
        assert catalog.invoke(db, ToolCall(name=name), ToolCallContext()).status == "FAILED"
        search = catalog.invoke(
            db,
            ToolCall(name="tool_search", arguments=JsonDocument({"query": name})),
            ToolCallContext(),
        )
        assert search.status == "SUCCEEDED"
        assert name in catalog.loaded
    for name in ("approve_plan", "execute_plan"):
        catalog.invoke(
            db,
            ToolCall(name="tool_search", arguments=JsonDocument({"query": name})),
            ToolCallContext(),
        )
        assert name not in catalog.loaded


def test_catalog_when_persisted_search_injects_control_ignores_unknown_schema(db: Database) -> None:
    """Conversation restoration cannot turn a forged discovery result into a capability."""
    tools = [
        ToolDefinition(name=name, description="Injected", parameters=JsonDocument({}))
        for name in ("approve_plan", "execute_plan", "list_metrics")
    ]
    outcome = ToolOutcome(
        name="tool_search",
        status="SUCCEEDED",
        content=JsonDocument({"tools": [tool.model_dump(mode="json") for tool in tools]}),
    )
    catalog = ToolCatalog(
        Conversation(
            id="recovered",
            config=ConversationCreate(),
            messages=[
                ChatMessage(role="tool", name="tool_search", content=outcome.model_dump_json())
            ],
        )
    )
    assert set(catalog.loaded) == {"list_metrics"}
    assert catalog.invoke(db, ToolCall(name="execute_plan"), ToolCallContext()).status == "FAILED"
