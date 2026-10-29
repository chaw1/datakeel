# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build MCP tool schemas from the same immutable domain argument models."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.actions.production_language import PRODUCTION_LANGUAGE
from datakeel.core.agent_models import ToolDefinition
from datakeel.core.ask_models import ASK_DATA_DESCRIPTION
from datakeel.core.llm_data_governance import TRAINING_QUALITY_DESCRIPTION
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.standard_functions import STANDARD_TOOL_DESCRIPTIONS
from datakeel.ontology.training_functions import TRAINING_TOOL_DESCRIPTIONS


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
    descriptions = {
        **STANDARD_TOOL_DESCRIPTIONS,
        **TRAINING_TOOL_DESCRIPTIONS,
        "get_training_quality": TRAINING_QUALITY_DESCRIPTION,
    }
    if name in descriptions:
        return descriptions[name]
    if name == "ask_data":
        return ASK_DATA_DESCRIPTION
    if name in PARAMETER_TYPES:
        base = f"Prepare {name}; return a frozen impact plan without executing it."
        language = PRODUCTION_LANGUAGE.get(name)
        return base + (" " + "; ".join(language) if language else "")
    return f"Read {name} without changing dataset contents."
