# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for validation."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.governance import compliance_score, template_schema, validate_metadata

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.fixture
def template() -> dict[str, JsonValue]:
    """Provide the template test fixture."""
    return {
        "name": "Research standard",
        "fields": {
            "owner": {"type": "string", "required": True, "pattern": "^[a-z]+$"},
            "license": {"type": "string", "required": True, "enum": ["Apache-2.0", "MIT"]},
            "count": {"type": "integer", "minimum": 1},
        },
    }


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"owner": "alice"}, "required"),
        ({"owner": "alice", "license": "unknown"}, "not one of"),
        ({"owner": "Alice 42", "license": "MIT"}, "does not match"),
        ({"owner": "alice", "license": "MIT", "count": "one"}, "integer"),
    ],
)
def test_required_enum_regex_and_types(
    template: dict[str, JsonValue], values: dict[str, JsonValue], expected: str
) -> None:
    """Verify required enum regex and types."""
    with pytest.raises(ValueError, match=expected):
        validate_metadata(template, values)


def test_valid_metadata_does_not_mutate_inputs(template: dict[str, JsonValue]) -> None:
    """Verify valid metadata does not mutate inputs."""
    values = {"owner": "alice", "license": "MIT", "count": 2}
    snapshot = deepcopy((template, values))
    assert validate_metadata(template, values) is None
    assert (template, values) == snapshot


def test_native_json_schema_and_wrapper_have_same_validation() -> None:
    """Verify native json schema and wrapper have same validation."""
    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer", "minimum": 2}},
        "required": ["value"],
        "additionalProperties": False,
    }
    for template in (schema, {"schema": schema}):
        validate_metadata(template, {"value": 2})
        with pytest.raises(ValueError, match=r".+"):
            validate_metadata(template, {"value": 1})
        with pytest.raises(ValueError, match=r".+"):
            validate_metadata(template, {"value": 2, "extra": True})


def test_remote_refs_and_invalid_schemas_rejected_without_network() -> None:
    """Verify remote refs and invalid schemas rejected without network."""
    with pytest.raises(ValueError, match="local schema references"):
        template_schema({"$ref": "https://example.test/schema"})
    with pytest.raises(ValueError, match="Invalid metadata template"):
        template_schema({"properties": {"x": {"type": "unsupported"}}})


def test_local_refs_work() -> None:
    """Verify local refs work."""
    schema = {
        "$defs": {"number": {"type": "integer"}},
        "properties": {"value": {"$ref": "#/$defs/number"}},
    }
    validate_metadata(schema, {"value": 1})
    with pytest.raises(ValueError, match=r".+"):
        validate_metadata(schema, {"value": "one"})


def test_compliance_weights_and_metadata_improvement(template: dict[str, JsonValue]) -> None:
    """Verify compliance weights and metadata improvement."""
    files = [FileItem(path="objects/a", filename="images/a.png", modality="image", size=1)]
    before = compliance_score("Example", files, {}, template)
    after = compliance_score(
        "Example", files, {"owner": "alice", "license": "MIT", "count": 1}, template
    )
    assert before["total"] == 70
    assert after["total"] == 100
    assert {key: value["weight"] for key, value in after["dimensions"].items()} == {
        "directory": 40,
        "naming": 30,
        "metadata": 30,
    }
    invalid = compliance_score(
        "Example", files, {"owner": "alice", "license": "unknown", "count": 1}, template
    )
    assert before["total"] < invalid["total"] < after["total"]


def test_directory_and_naming_rules_are_explainable() -> None:
    """Verify directory and naming rules are explainable."""
    files = [FileItem(path="objects/a", filename="../bad?.txt", size=1)]
    result = compliance_score("Bad?", files, {}, {"schema": {"type": "object"}})
    assert result["dimensions"]["directory"]["score"] == 0
    assert result["dimensions"]["naming"]["score"] == 0
    assert result["total"] == 30


def test_top_level_constraints_reduce_metadata_score() -> None:
    """Verify top level constraints reduce metadata score."""
    template = {
        "schema": {
            "type": "object",
            "properties": {"owner": {"type": "string"}},
            "additionalProperties": False,
        }
    }
    result = compliance_score("Example", [], {"owner": "alice", "extra": True}, template)
    assert result["dimensions"]["metadata"]["score"] == 0


@pytest.mark.parametrize("reference", ["#/$defs/missing", "#missing_anchor", "#/title"])
def test_invalid_local_references_are_rejected_when_binding(reference: str) -> None:
    """Verify invalid local references are rejected when binding."""
    schema = {"title": "Example", "properties": {"value": {"$ref": reference}}}
    with pytest.raises(ValueError, match="Invalid metadata template"):
        template_schema(schema)


def test_local_anchor_reference_remains_supported() -> None:
    """Verify local anchor reference remains supported."""
    schema = {
        "$defs": {"value": {"$anchor": "number", "type": "integer"}},
        "properties": {"value": {"$ref": "#number"}},
    }
    validate_metadata(schema, {"value": 2})
    with pytest.raises(ValueError, match=r".+"):
        validate_metadata(schema, {"value": "two"})
