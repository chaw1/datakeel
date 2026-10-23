# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate source and wheel specialist contracts before any model is called."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.registry import action_definitions
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.delegation.models import AgentDefinition
from datakeel.ontology.functions import function_definitions


def agents_path() -> Path:
    """Find identical bundled contracts from a checkout or installed wheel."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "agents"
    return source if source.exists() else package / "_contracts" / "agents"


def _read(path: Path) -> AgentDefinition:
    try:
        definition = AgentDefinition.model_validate(yaml.safe_load(path.read_text()))
    except ModelValidationError as error:
        located = [
            f"{path.name}:{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors()
        ]
        raise ValidationError("; ".join(located)) from error
    except (OSError, yaml.YAMLError) as error:
        msg = f"{path.name}:document: {error}"
        raise ValidationError(msg) from error
    actions = {item.id: item for item in action_definitions()}
    known = (
        {item.id for item in function_definitions()}
        | actions.keys()
        | {"tool_search", "delegate_agent"}
    )
    for index, tool in enumerate(definition.tools):
        reason = "unknown tool" if tool not in known else ""
        if tool in actions and not actions[tool].reversible:
            reason = "irreversible actions are forbidden"
        if reason:
            msg = f"{path.name}:tools.{index}: {tool}: {reason}"
            raise ValidationError(msg)
    return definition


def list_agents(directory: Path | None = None) -> list[AgentDefinition]:
    """Reject malformed or duplicate definitions with file and field locations."""
    definitions: list[AgentDefinition] = []
    names: set[str] = set()
    for path in sorted((directory or agents_path()).glob("*.yaml")):
        definition = _read(path)
        if definition.name in names:
            msg = f"{path.name}:name: duplicate agent {definition.name}"
            raise ValidationError(msg)
        names.add(definition.name)
        definitions.append(definition)
    if not definitions:
        msg = "agents:document: no agent definitions found"
        raise ValidationError(msg)
    return definitions


def get_agent(name: str) -> AgentDefinition:
    """Resolve only registered names, never paths supplied by a model."""
    for definition in list_agents():
        if definition.name == name:
            return definition
    msg = f"Unknown delegated agent: {name}"
    raise NotFoundError(msg)
