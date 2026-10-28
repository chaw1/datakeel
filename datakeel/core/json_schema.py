# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compact model-visible JSON Schema without changing accepted arguments or defaults."""

from pydantic import JsonValue

from datakeel.core.models import JsonDocument

_NULLABLE_VARIANT_COUNT = 2


def _compact_union(schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
    variants = schema.get("anyOf")
    if "type" in schema or not isinstance(variants, list) or not variants:
        return schema
    if all(
        isinstance(item, dict) and set(item) == {"type"} and isinstance(item["type"], str)
        for item in variants
    ):
        kinds = sorted({str(item["type"]) for item in variants if isinstance(item, dict)})
        return JsonDocument.model_validate(
            {**{key: value for key, value in schema.items() if key != "anyOf"}, "type": kinds}
        ).root
    if len(variants) != _NULLABLE_VARIANT_COUNT or {"type": "null"} not in variants:
        return schema
    typed = next(item for item in variants if item != {"type": "null"})
    keywords = {
        "type",
        "enum",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "format",
    }
    if (
        not isinstance(typed, dict)
        or typed.get("type") not in ("string", "number", "integer", "boolean")
        or not typed.keys() <= keywords
        or typed.keys() & schema.keys()
    ):
        return schema
    result = {**{key: value for key, value in schema.items() if key != "anyOf"}, **typed}
    result["type"] = [typed["type"], "null"]
    enumeration = typed.get("enum")
    if isinstance(enumeration, list):
        result["enum"] = [*enumeration, None]
    return result


def _compact(schema: JsonValue, *, field: bool = False) -> JsonValue:
    if not isinstance(schema, dict):
        return schema
    result: dict[str, JsonValue] = {}
    for key, value in schema.items():
        if key == "title" or (key == "description" and not field):
            continue
        if key in {"properties", "patternProperties", "$defs", "definitions"} and isinstance(
            value, dict
        ):
            result[key] = {
                name: _compact(item, field=key in {"properties", "patternProperties"})
                for name, item in value.items()
            }
        elif key in {"anyOf", "allOf", "oneOf", "prefixItems"} and isinstance(value, list):
            result[key] = [_compact(item, field=True) for item in value]
        elif key in {"items", "additionalProperties", "not", "if", "then", "else"}:
            result[key] = _compact(value, field=True)
        else:
            result[key] = value
    return _compact_union(result)


def compact_schema(schema: JsonDocument) -> JsonDocument:
    """Keep field explanations and validation keywords while removing repeated model labels."""
    return JsonDocument.model_validate(_compact(schema.root))
