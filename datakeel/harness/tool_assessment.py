# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assert measured tool payloads without trusting assistant-written summaries."""

from jsonschema import Draft202012Validator, ValidationError, validate
from pydantic import ValidationError as ModelValidationError

from datakeel.core.harness_eval import ExpectedToolResult, ObservedToolResult
from datakeel.core.models import AssetRef
from datakeel.ontology.models import FunctionResult


def selection_refs(observation: ObservedToolResult) -> list[AssetRef]:
    """Read selected function outputs separately from the audit's broader dependency refs."""
    try:
        return FunctionResult.model_validate(observation.content.root).asset_refs
    except ModelValidationError:
        return []


def tool_failures(
    expectations: list[ExpectedToolResult], observations: list[ObservedToolResult]
) -> list[str]:
    """Require the named successful calls and validate their actual response structures."""
    failures: list[str] = []
    for expected in expectations:
        matches = [item for item in observations if item.name == expected.name]
        if len(matches) != expected.calls:
            failures.append(f"Tool result count mismatch: {expected.name}")
        if expected.call_index is not None:
            if expected.call_index >= len(matches):
                failures.append(f"Tool result index missing: {expected.name}")
                continue
            matches = [matches[expected.call_index]]
        for item in matches:
            if item.status != expected.status:
                failures.append(f"Tool result status mismatch: {expected.name}")
            if expected.asset_refs_required and not item.asset_refs:
                failures.append(f"Tool result lacks asset references: {expected.name}")
            try:
                validate(item.content.root, expected.content_schema.root, cls=Draft202012Validator)
            except ValidationError as error:
                path = ".".join(str(value) for value in error.absolute_path)
                failures.append(
                    f"Tool content mismatch: {expected.name} at {path}: {error.message}"
                )
    return failures
