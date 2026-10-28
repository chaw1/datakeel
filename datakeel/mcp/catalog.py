# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build MCP tool schemas from the same immutable domain argument models."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.agent_models import ToolDefinition
from datakeel.core.ask_models import ASK_DATA_DESCRIPTION
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.standard_functions import STANDARD_TOOL_DESCRIPTIONS
from datakeel.ontology.tool_models import ApproveToolParams, ExecuteToolParams
from datakeel.ontology.training_functions import TRAINING_TOOL_DESCRIPTIONS


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
    descriptions = {**STANDARD_TOOL_DESCRIPTIONS, **TRAINING_TOOL_DESCRIPTIONS}
    if name in descriptions:
        return descriptions[name]
    if name == "ask_data":
        return ASK_DATA_DESCRIPTION
    if name in PARAMETER_TYPES:
        return f"Prepare {name}; return a frozen impact plan without executing it."
    if name == "approve_plan":
        return "Record an explicit human approval or rejection bound to the exact plan digest."
    if name == "execute_plan":
        return "Execute a prepared plan once, enforcing required approval and frozen target state."
    return f"Read {name} without changing dataset contents."
