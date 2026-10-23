# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve JSON references and a deliberately small pure expression vocabulary."""

import json
import re
from collections.abc import Iterator

from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.workflows.models import Comparison

REFERENCE = re.compile(r"\$\{((?:inputs|steps)\.[a-zA-Z0-9_.-]+)\}")
PATH = re.compile(r"^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*$")
FUNCTION_ARGUMENTS = 2
FUNCTIONS = frozenset({"$merge", "$equals", "$rows_equal", "$pluck"})


def references(value: JsonValue) -> Iterator[str]:
    """Yield references from nested JSON without executing any expression."""
    if isinstance(value, str):
        yield from REFERENCE.findall(value)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from references(item)


def expression_errors(value: JsonValue) -> list[str]:
    """Reject malformed references and non-allowlisted function-shaped objects."""
    if isinstance(value, str):
        return ["malformed reference"] if "${" in REFERENCE.sub("", value) else []
    if isinstance(value, list):
        return [error for item in value for error in expression_errors(item)]
    if not isinstance(value, dict):
        return []
    return _object_expression_errors(value)


def _object_expression_errors(value: dict[str, JsonValue]) -> list[str]:
    reserved = [key for key in value if key.startswith("$")]
    if reserved:
        if len(value) != 1 or reserved[0] not in FUNCTIONS:
            return ["unknown output function"]
        arguments = value[reserved[0]]
        if not isinstance(arguments, list) or len(arguments) != FUNCTION_ARGUMENTS:
            return ["pure functions require exactly two arguments"]
        if reserved[0] == "$pluck" and (
            not isinstance(arguments[1], str) or not PATH.fullmatch(arguments[1])
        ):
            return ["pluck requires a literal property path"]
    return [error for item in value.values() for error in expression_errors(item)]


def lookup(value: JsonValue, path: str) -> JsonValue:
    """Read explicit object keys and numeric array indexes without attribute access."""
    current = value
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            msg = f"Unknown workflow reference: {path}"
            raise ValidationError(msg)
    return current


def _merge(base: JsonValue, override: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(base, dict) or not isinstance(override, dict):
        msg = "merge requires two objects"
        raise ValidationError(msg)
    merged = dict(base)
    for key, value in override.items():
        previous = merged.get(key)
        merged[key] = (
            _merge(previous, value)
            if isinstance(previous, dict) and isinstance(value, dict)
            else value
        )
    return merged


def _function(name: str, arguments: list[JsonValue]) -> JsonValue:
    left, right = arguments
    if name == "$merge":
        return _merge(left, right)
    if name == "$pluck":
        if not isinstance(left, list) or not isinstance(right, str):
            msg = "pluck requires an array and a property path"
            raise ValidationError(msg)
        return [lookup(item, right) for item in left]
    if name == "$rows_equal" and (not isinstance(left, list) or not isinstance(right, list)):
        msg = "rows_equal requires two row arrays"
        raise ValidationError(msg)
    return left == right


def resolve(value: JsonValue, inputs: JsonDocument, outputs: JsonDocument) -> JsonValue:
    """Render a JSON template while preserving the type of complete references."""
    errors = expression_errors(value)
    if errors:
        raise ValidationError("; ".join(errors))
    context: dict[str, JsonValue] = {"inputs": inputs.root, "steps": outputs.root}
    return _resolve(value, context)


def _resolve(value: JsonValue, context: dict[str, JsonValue]) -> JsonValue:
    if isinstance(value, str):
        match = REFERENCE.fullmatch(value)
        if match:
            return lookup(context, match[1])
        return REFERENCE.sub(lambda match: _text(lookup(context, match[1])), value)
    if isinstance(value, list):
        return [_resolve(item, context) for item in value]
    if isinstance(value, dict):
        function = next((key for key in value if key in FUNCTIONS), None)
        if function is not None:
            arguments = _resolve(value[function], context)
            if isinstance(arguments, list):
                return _function(function, arguments)
        return {key: _resolve(item, context) for key, item in value.items()}
    return value


def _text(value: JsonValue) -> str:
    return (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )


def compare(left: JsonValue, op: Comparison, right: JsonValue) -> bool:
    """Evaluate a closed comparator set without evaluating expression source."""
    if op in {"eq", "ne"}:
        return (left == right) if op == "eq" else (left != right)
    if op == "in":
        if isinstance(right, list):
            return left in right
        msg = "in requires an array operand"
        raise ValidationError(msg)
    if isinstance(left, bool) or isinstance(right, bool):
        msg = "ordered comparisons require numeric operands"
        raise ValidationError(msg)
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        msg = "ordered comparisons require numeric operands"
        raise ValidationError(msg)
    return {"lt": left < right, "lte": left <= right, "gt": left > right, "gte": left >= right}[op]
