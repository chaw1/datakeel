# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resident evidence reads share typed queries, explanations, and asset auditing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.tools import ToolCatalog, resident_tools
from datakeel.core.agent_models import Conversation, ConversationCreate, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceExplanation, EvidenceQueryResult
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import ObjectSet
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.tool_invocations import list_invocations
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_evidence_schema_when_resident_restricts_files_without_narrowing_object_sets() -> None:
    """The model-visible evidence schema matches validation while ordinary selections stay broad."""
    query = next(tool for tool in resident_tools() if tool.name == "query_evidence")
    properties = query.parameters.root["properties"]
    assert isinstance(properties, dict)
    object_type = properties["object_type"]
    assert isinstance(object_type, dict)
    assert object_type["enum"] == ["file"]
    assert ObjectSet.model_json_schema()["properties"]["object_type"]["type"] == "string"
    for kind in ("dataset", "version", "file", "artifact", "task"):
        assert ObjectSet(object_type=kind).object_type == kind


def test_evidence_functions_when_read_by_agent_are_resident_and_preserve_unknown(
    db: Database, tmp_path: Path
) -> None:
    """Missing annotations remain unknown through Agent tools, explanation, and audit."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    version, files = source_manifest(db, dataset)
    sample = next(item for item in files if "scene-0018" in item.filename)
    names = {tool.name for tool in resident_tools()}
    assert {"query_evidence", "get_evidence", "explain_sample"} <= names
    catalog = ToolCatalog(Conversation(id="evidence-agent", config=ConversationCreate()))
    for name in ("get_evidence", "explain_sample"):
        result = catalog.invoke(
            db,
            ToolCall(name=name, arguments=JsonDocument({"asset_id": sample.id})),
            ToolCallContext(agent_id="fixture", session_id="evidence-agent"),
        )
        assert result.status == "SUCCEEDED", result.error
        assert any(
            ref.asset_type == "file" and ref.asset_id == sample.id and ref.version == version
            for ref in result.asset_refs
        )
        assert not any(
            ref.asset_type == "dataset" and ref.asset_id == sample.id for ref in result.asset_refs
        )
        if name == "explain_sample":
            explanation = EvidenceExplanation.model_validate(result.content.root["data"])
            assert "unknown" in explanation.text
            assert any(state.value == "unknown" for state in explanation.states)
            assert explanation.assertions
    invocations = list_invocations(db, "evidence-agent")
    assert len(invocations) == 2
    assert all(item.status == "SUCCEEDED" and item.asset_refs for item in invocations)


def test_query_function_when_empty_keeps_explicit_dataset_and_version_scope_refs(
    db: Database, tmp_path: Path
) -> None:
    """An empty selection still audits the assets explicitly addressed by the request."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    version, _ = source_manifest(db, dataset)
    for scope in ({"dataset_id": dataset}, {"version_ids": [version]}):
        result = invoke_function(
            db,
            "query_evidence",
            JsonDocument.model_validate(
                {**scope, "filters": [{"field": "filename", "value": "never-matches"}]}
            ),
        )
        assert EvidenceQueryResult.model_validate(result.data).items == []
        assert result.asset_refs
        assert result.asset_refs[0].asset_id == (dataset if "dataset_id" in scope else version)


def test_query_function_when_store_empty_returns_empty_typed_result(db: Database) -> None:
    """Unscoped empty-store reads have no affected asset to invent for audit."""
    result = invoke_function(db, "query_evidence", JsonDocument({}))
    assert EvidenceQueryResult.model_validate(result.data).items == []
    assert result.asset_refs == []
