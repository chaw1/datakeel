# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound a deliberately small JSON Schema vocabulary before host-side validation."""

import json

from jsonschema import Draft202012Validator, validate
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument

_MAX_DEPTH = 8
_MAX_KEY_LENGTH = 256
_MAX_SCHEMA_NODES = 256
_MAX_VALUE_NODES = 4096
_MAX_BYTES = 65536
_ALLOWED = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "items",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "title",
    "description",
    "default",
}
_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def _bounded_json(value: JsonValue, max_nodes: int) -> None:
    pending: list[tuple[JsonValue, int]] = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > max_nodes or depth > _MAX_DEPTH:
            msg = "Custom JSON exceeds the node or nesting limit"
            raise ValidationError(msg)
        children: list[JsonValue] = []
        if isinstance(current, dict):
            children = list(current.values()) if len(current) <= max_nodes else []
            invalid = len(current) > max_nodes or any(len(key) > _MAX_KEY_LENGTH for key in current)
        elif isinstance(current, list):
            children = current if len(current) <= max_nodes else []
            invalid = len(current) > max_nodes
        else:
            invalid = isinstance(current, str) and len(current) > _MAX_BYTES
        if invalid:
            msg = "Custom JSON contains an oversized value"
            raise ValidationError(msg)
        pending.extend((child, depth + 1) for child in children)
    try:
        size = len(json.dumps(value, allow_nan=False, ensure_ascii=False).encode())
    except ValueError as exc:
        msg = "Custom JSON must contain finite numbers"
        raise ValidationError(msg) from exc
    if size > _MAX_BYTES:
        msg = "Custom JSON exceeds the serialized byte limit"
        raise ValidationError(msg)


def _schema_nodes(schema: dict[str, JsonValue]) -> None:
    kind = schema.get("type")
    if set(schema) - _ALLOWED or not isinstance(kind, str) or kind not in _TYPES:
        msg = "Custom schemas require a single supported type and restricted keywords"
        raise ValidationError(msg)
    if not isinstance(schema.get("additionalProperties", False), bool):
        msg = "Custom additionalProperties must be a boolean"
        raise ValidationError(msg)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        msg = "Custom schema properties must be an object"
        raise ValidationError(msg)
    for child in properties.values():
        if not isinstance(child, dict):
            msg = "Custom property schemas must be objects"
            raise ValidationError(msg)
        _schema_nodes(child)
    items = schema.get("items")
    if items is not None:
        if not isinstance(items, dict):
            msg = "Custom array items must be one schema object"
            raise ValidationError(msg)
        _schema_nodes(items)


def validate_custom_schema(schema: JsonDocument) -> None:
    """Reject regexes, references, combinators, and excessive schema complexity."""
    _bounded_json(schema.root, _MAX_SCHEMA_NODES)
    _schema_nodes(schema.root)
    if schema.root.get("type") != "object":
        msg = "Custom parameter and metadata schemas must describe objects"
        raise ValidationError(msg)
    try:
        Draft202012Validator.check_schema(schema.root)
    except SchemaError as exc:
        msg = "Invalid custom JSON Schema"
        raise ValidationError(msg) from exc


def validate_custom_values(schema: JsonDocument, values: JsonDocument) -> None:
    """Validate bounded JSON against a freshly verified, non-executable schema subset."""
    validate_custom_schema(schema)
    _bounded_json(values.root, _MAX_VALUE_NODES)
    try:
        validate(values.root, schema.root)
    except (SchemaValidationError, ValueError) as exc:
        msg = "Custom operator values violate their declared schema"
        raise ValidationError(msg) from exc
