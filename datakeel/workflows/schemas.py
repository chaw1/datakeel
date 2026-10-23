# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate static argument parts and referenced fields against registered schemas."""

from pydantic import BaseModel, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.models import ActionRun
from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.ask_models import AskAnswer
from datakeel.core.metric_models import MetricCard
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQueryResult
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.models import FrozenManifest, FunctionResult
from datakeel.quality.models import QualityView, ReportView
from datakeel.workflows.models import ApprovalStep, Step, ToolStep
from datakeel.workflows.resolver import FUNCTIONS, REFERENCE

OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "get_quality": QualityView,
    "get_report": ReportView,
    "search_files": FrozenManifest,
    "explain_metric": MetricCard,
    "ask_data": AskAnswer,
    "query_evidence": EvidenceQueryResult,
}


def _dynamic(value: JsonValue) -> bool:
    return (isinstance(value, str) and REFERENCE.search(value) is not None) or (
        isinstance(value, dict) and bool(FUNCTIONS.intersection(value))
    )


def _deferred(arguments: JsonValue, location: tuple[int | str, ...]) -> bool:
    current = arguments
    for key in location:
        if _dynamic(current):
            return True
        if isinstance(current, dict) and isinstance(key, str):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return False
    return _contains_dynamic(current)


def _contains_dynamic(value: JsonValue) -> bool:
    if _dynamic(value):
        return True
    if isinstance(value, dict):
        return any(_contains_dynamic(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_dynamic(item) for item in value)
    return False


def argument_errors(name: str, arguments: JsonDocument) -> list[str]:
    """Validate literals now and defer only fields supplied by declared expressions."""
    model = PARAMETER_MODELS.get(name) or PARAMETER_TYPES.get(name)
    if model is None:
        return [f"unknown tool: {name}"]
    try:
        model.model_validate(arguments.root)
    except ModelValidationError as error:
        return [
            f"arguments.{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors()
            if not _deferred(arguments.root, item["loc"])
        ]
    return []


def output_has_path(step: Step, path: list[str]) -> bool:
    """Check known read and action output properties without inventing dynamic schemas."""
    if not path or not isinstance(step, ToolStep | ApprovalStep):
        return True
    name = step.tool if isinstance(step, ToolStep) else step.action
    model: type[BaseModel] = ActionRun if name in PARAMETER_TYPES else FunctionResult
    if name in OUTPUT_MODELS and path[0] == "data":
        model = OUTPUT_MODELS[name]
        path = path[1:]
    schema = JsonDocument.model_validate(model.model_json_schema())
    return _has_path(schema.root, schema.root, path)


def _has_path(schema: JsonValue, root: JsonValue, path: list[str]) -> bool:
    if not path or not isinstance(schema, dict):
        return True
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/") and isinstance(root, dict):
        definitions = root.get("$defs")
        if isinstance(definitions, dict):
            return _has_path(definitions.get(reference.removeprefix("#/$defs/")), root, path)
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list):
        return any(
            _has_path(item, root, path)
            for item in alternatives
            if isinstance(item, dict) and item.get("type") != "null"
        )
    return _property_path(schema, root, path)


def _property_path(schema: dict[str, JsonValue], root: JsonValue, path: list[str]) -> bool:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return path[0] in properties and _has_path(properties[path[0]], root, path[1:])
    if schema.get("type") == "array":
        return path[0].isdigit() and _has_path(schema.get("items"), root, path[1:])
    if schema.get("type") in {"string", "number", "integer", "boolean", "null"}:
        return False
    return _has_path(schema.get("additionalProperties"), root, path[1:])
