# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure standard-template normalization and metadata validation."""

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as SchemaValidationError
from referencing import Registry, Resource
from referencing._core import Resolver
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012, UnknownDialect

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

DEFAULT_TEMPLATE: dict[str, Any] = {
    "name": "Dataset essentials",
    "schema": {
        "type": "object",
        "properties": {
            "description": {"type": "string", "minLength": 1},
            "license": {"type": "string", "minLength": 1},
            "creator": {"type": "string", "minLength": 1},
        },
        "required": ["description", "license", "creator"],
    },
}


def _reject_external_refs(value: object) -> None:
    if isinstance(value, dict):
        for key, child in cast("dict[str, Any]", value).items():
            if key in {"$ref", "$dynamicRef"} and (
                not isinstance(child, str) or not child.startswith("#")
            ):
                msg = "Metadata templates may only use local schema references"
                raise ValidationError(msg)
            _reject_external_refs(child)
    elif isinstance(value, list):
        for child in cast("list[Any]", value):
            _reject_external_refs(child)


def _check_local_references(schema: dict[str, Any]) -> None:
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resolver = Registry[Any]().resolver_with_root(resource)

    def visit(current: Resource[Any], context: Resolver[Any]) -> None:
        contents: Any = current.contents
        if isinstance(contents, dict):
            contents = cast("dict[str, Any]", contents)
            for key in ("$ref", "$dynamicRef"):
                if key in contents:
                    resolved = context.lookup(contents[key])
                    Draft202012Validator.check_schema(resolved.contents)
        for child in current.subresources():
            visit(child, context.in_subresource(child))

    visit(resource, resolver)


def template_schema(template: dict[str, Any] | JsonDocument) -> JsonDocument:
    """Accept a JSON Schema, {schema: ...}, or a convenient fields dictionary."""
    if isinstance(template, JsonDocument):
        template = template.root
    if "schema" in template:
        schema = deepcopy(template["schema"])
    elif "fields" in template:
        schema = _fields_schema(template)
    else:
        schema = deepcopy(template)
    if not isinstance(schema, dict):
        msg = "Template schema must be an object"
        raise ValidationError(msg)
    schema = cast("dict[str, Any]", schema)
    schema.setdefault("type", "object")
    if schema["type"] != "object":
        msg = "Metadata template must describe an object"
        raise ValidationError(msg)
    _reject_external_refs(schema)
    try:
        Draft202012Validator.check_schema(schema)
        _check_local_references(schema)
    except (SchemaError, Unresolvable, UnknownDialect) as error:
        msg = f"Invalid metadata template: {error}"
        raise ValidationError(msg) from error
    return JsonDocument.model_validate(schema)


def validate_metadata(template: dict[str, Any], values: dict[str, Any]) -> None:
    """Validate metadata against a checked, exclusively local JSON Schema."""
    schema = template_schema(template)
    errors = sorted(
        validation_errors(schema.root, values),
        key=lambda error: str(list(error.path)),
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.path)) or '$'}: {error.message}" for error in errors
        )
        msg = f"Invalid metadata: {details}"
        raise ValidationError(msg)


def validation_errors(
    schema: dict[str, Any], values: dict[str, Any]
) -> list[SchemaValidationError]:
    """Collect JSON Schema failures through the library's dynamic validator boundary."""
    validator: Any = Draft202012Validator(schema, format_checker=FormatChecker())
    inspect = cast(
        "Callable[[dict[str, Any]], Iterable[SchemaValidationError]]", validator.iter_errors
    )
    return list(inspect(values))


def _fields_schema(template: dict[str, Any]) -> dict[str, Any]:
    fields = template["fields"]
    if not isinstance(fields, dict):
        msg = "Template fields must be an object"
        raise ValidationError(msg)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field, definition in cast("dict[str, Any]", fields).items():
        if not isinstance(definition, dict):
            msg = f"Invalid field definition: {field}"
            raise ValidationError(msg)
        definition = cast("dict[str, Any]", definition)
        properties[field] = {
            key: deepcopy(value) for key, value in definition.items() if key != "required"
        }
        if definition.get("required"):
            required.append(field)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": template.get("additionalProperties", True),
    }
