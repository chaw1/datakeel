# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound schema complexity and values before host-side validation of custom code data."""

import pytest

from datakeel.core.custom_schema import validate_custom_schema, validate_custom_values
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "patternProperties": {"(a+)+$": {"type": "string"}}},
        {"type": "object", "properties": {"name": {"type": "string", "pattern": "(a+)+$"}}},
        {"type": "object", "allOf": [{"type": "object"}]},
        {"type": ["object", "null"]},
        {"type": "object", "additionalProperties": {"type": "string"}},
        {"type": "object", "properties": []},
        {"type": "object", "properties": {"field": True}},
        {"type": "object", "properties": {"field": {"type": "array", "items": []}}},
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "required": 1},
    ],
)
def test_schema_when_executable_or_unsupported_vocabulary_is_rejected(schema: object) -> None:
    """Regexes, combinators, references, and malformed shapes never reach a validator."""
    with pytest.raises(ValidationError):
        validate_custom_schema(JsonDocument.model_validate(schema))


def test_values_when_safe_nested_schema_applies_numeric_and_length_bounds() -> None:
    """Restricted arrays and object properties retain useful declarative constraints."""
    schema = JsonDocument(
        {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "maxItems": 3,
                },
                "label": {"type": "string", "minLength": 1, "enum": ["ready", "done"]},
            },
            "required": ["values", "label"],
            "additionalProperties": False,
        }
    )
    validate_custom_values(schema, JsonDocument({"values": [1, 2], "label": "ready"}))
    with pytest.raises(ValidationError, match="schema"):
        validate_custom_values(schema, JsonDocument({"values": [0], "label": "ready"}))


@pytest.mark.parametrize(
    "values",
    [
        {"field": float("nan")},
        {"field": "x" * 65537},
        {"x" * 257: 1},
        {"field": list(range(4097))},
        {str(index): 1 for index in range(4097)},
        {"field": ["x" * 40000, "y" * 40000]},
        {"field": {str(index): list(range(100)) for index in range(100)}},
    ],
)
def test_values_when_oversized_or_nonfinite_is_rejected(values: object) -> None:
    """A valid open metadata schema does not bypass byte, node, or finite-value bounds."""
    with pytest.raises(ValidationError):
        validate_custom_values(
            JsonDocument({"type": "object"}), JsonDocument.model_validate(values)
        )


def test_values_when_excessive_nesting_is_rejected() -> None:
    """Host validation cannot recurse through arbitrarily nested output metadata."""
    values = JsonDocument({"field": []})
    for _ in range(9):
        values = JsonDocument({"nested": values.root})
    with pytest.raises(ValidationError, match="nesting"):
        validate_custom_values(JsonDocument({"type": "object"}), values)


def test_schema_when_too_many_properties_is_rejected() -> None:
    """Schema size is bounded independently of parameter document size."""
    schema = JsonDocument.model_validate(
        {
            "type": "object",
            "properties": {f"field_{index}": {"type": "string"} for index in range(257)},
        }
    )
    with pytest.raises(ValidationError):
        validate_custom_schema(schema)
