# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build MCP tool schemas from the same immutable domain argument models."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.agent_models import ToolDefinition
from datakeel.core.ask_models import ASK_DATA_DESCRIPTION
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.standard_functions import STANDARD_TOOL_DESCRIPTIONS


def tool_definitions() -> list[ToolDefinition]:
    """Describe registered reads and prepare-only actions; approval and execution stay human."""
    models = {**PARAMETER_MODELS, **PARAMETER_TYPES}
    return [
        ToolDefinition(
            name=name,
            description=_description(name),
            parameters=JsonDocument.model_validate(model.model_json_schema()),
        )
        for name, model in models.items()
    ]


def _description(name: str) -> str:
    if name in STANDARD_TOOL_DESCRIPTIONS:
        return STANDARD_TOOL_DESCRIPTIONS[name]
    if name == "ask_data":
        return ASK_DATA_DESCRIPTION
    if name in PARAMETER_TYPES:
        return f"Prepare {name}; return a frozen impact plan without executing it."
    return f"Read {name} without changing dataset contents."
