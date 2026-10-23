# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build MCP tool schemas from the same immutable domain argument models."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.agent_models import ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ApproveToolParams, ExecuteToolParams


def tool_definitions() -> list[ToolDefinition]:
    """Describe registered reads, prepare-only actions, and two explicit controls."""
    models = {
        **PARAMETER_MODELS,
        **PARAMETER_TYPES,
        "approve_plan": ApproveToolParams,
        "execute_plan": ExecuteToolParams,
    }
    return [
        ToolDefinition(
            name=name,
            description=_description(name),
            parameters=JsonDocument.model_validate(model.model_json_schema()),
        )
        for name, model in models.items()
    ]


def _description(name: str) -> str:
    if name in PARAMETER_TYPES:
        return f"Prepare {name}; return a frozen impact plan without executing it."
    if name == "approve_plan":
        return "Record an explicit human approval or rejection bound to the exact plan digest."
    if name == "execute_plan":
        return "Execute a prepared plan once, enforcing required approval and frozen target state."
    return f"Read {name} without changing dataset contents."
