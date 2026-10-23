# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Agent schema compaction preserves argument validation and meaningful field descriptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validate

from datakeel.agent.schemas import compact_schema
from datakeel.agent.tools import ToolCatalog, deferred_tools, resident_tools
from datakeel.core.agent_models import Conversation, ConversationCreate, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.functions import function_definitions
from datakeel.ontology.tool_models import ToolCallContext

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import JsonValue

    from datakeel.storage.database import Database


def _accepts(schema: JsonDocument, arguments: Mapping[str, JsonValue]) -> bool:
    try:
        validate(arguments, schema.root, cls=Draft202012Validator, format_checker=FormatChecker())
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"page_size": 0},
        {"page_size": 200},
        {"page_size": 201},
        {"quality_min": None, "split": None},
        {"quality_min": -1},
        {"quality_max": 101},
        {"split": "train"},
        {"split": "wrong"},
        {"cursor": ""},
        {"cursor": None},
        {"created_after": "not-a-date"},
        {"created_after": "2026-10-22T00:00:00Z"},
        {"object_type": "dataset"},
        {"unexpected": True},
        {"assertion_filters": [{"predicate": "mentions", "status": ["rejected"]}]},
        {"assertion_filters": [{"predicate": "invalid"}]},
        {"assertion_filters": [{"predicate": "mentions", "min_confidence": 1.1}]},
    ],
)
def test_evidence_schema_when_compacted_preserves_boundary_validation(
    arguments: dict[str, JsonValue],
) -> None:
    """Nullable fields, bounds, enums, required values, and formats accept identical inputs."""
    original = JsonDocument.model_validate(EvidenceQuery.model_json_schema())
    compact = compact_schema(original)
    Draft202012Validator.check_schema(compact.root)
    assert _accepts(compact, arguments) == _accepts(original, arguments)
    assert len(compact.model_dump_json()) < len(original.model_dump_json())


def test_schema_when_property_names_overlap_annotations_keeps_values_and_field_explanations() -> (
    None
):
    """Do not delete user properties or defaults merely because their keys name schema metadata."""
    original = JsonDocument.model_validate(
        {
            "title": "Fixture",
            "description": "Repeated object label",
            "type": "object",
            "additionalProperties": False,
            "required": ["title"],
            "properties": {
                "title": {"type": "string", "minLength": 3, "description": "Display title"},
                "description": {"type": "string", "enum": ["title", "description"]},
                "settings": {"type": "object", "default": {"title": "Keep", "description": "Me"}},
                "bounded": {"type": "integer", "anyOf": [{"type": "number"}, {"type": "string"}]},
                "custom": {"anyOf": [{"$ref": "#/$defs/value"}, {"type": "null"}]},
            },
            "$defs": {"value": {"type": "string", "pattern": "^ok$"}},
        }
    )
    compact = compact_schema(original)
    properties = compact.root["properties"]
    assert isinstance(properties, dict)
    assert properties == original.root["properties"]
    assert "title" not in compact.root
    for arguments in ({"title": "ok"}, {"title": "valid"}, {"title": "valid", "bounded": "bad"}):
        assert _accepts(compact, arguments) == _accepts(original, arguments)


def test_agent_schema_when_assembled_keeps_public_contracts_untouched() -> None:
    """Only model-visible tools use compact schemas; public function schemas retain annotations."""
    original = next(item for item in function_definitions() if item.id == "query_evidence")
    tool = next(item for item in resident_tools() if item.name == original.id)
    assert "title" in original.input_schema.root
    assert "title" not in tool.parameters.root
    assert tool.description
    for item in [*resident_tools(), *deferred_tools()]:
        Draft202012Validator.check_schema(item.parameters.root)


def test_tool_discovery_when_exact_name_requested_avoids_overlapping_action_schemas(
    db: Database,
) -> None:
    """An exact action name loads one schema while a partial name still discovers both inverses."""
    for query, expected in (
        ("quarantine_files", {"quarantine_files"}),
        ("quarantine", {"quarantine_files", "unquarantine_files"}),
    ):
        catalog = ToolCatalog(Conversation(id="schema-search", config=ConversationCreate()))
        outcome = catalog.invoke(
            db,
            ToolCall(name="tool_search", arguments=JsonDocument({"query": query})),
            ToolCallContext(),
        )
        assert outcome.status == "SUCCEEDED"
        assert set(catalog.loaded) == expected
