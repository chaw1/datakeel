# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load source-tree or wheel workflow contracts and bind validated user inputs."""

from pathlib import Path

import yaml
from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.workflows.models import WorkflowDefinition, WorkflowInput
from datakeel.workflows.validation import validate_definition


def workflows_path() -> Path:
    """Locate checked-in contracts or the identical wheel resources."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "workflows"
    return source if source.exists() else package / "_contracts" / "workflows"


def _read(path: Path) -> tuple[WorkflowDefinition | None, list[str]]:
    try:
        return WorkflowDefinition.model_validate(yaml.safe_load(path.read_text())), []
    except ModelValidationError as error:
        return None, [
            f"{path.name}:{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors()
        ]
    except (OSError, yaml.YAMLError) as error:
        return None, [f"{path.name}:document: {error}"]


def _type_matches(spec: WorkflowInput, value: JsonValue) -> bool:
    if spec.type in {"number", "integer"}:
        return not isinstance(value, bool) and isinstance(
            value, int if spec.type == "integer" else (int, float)
        )
    return isinstance(
        value, {"string": str, "boolean": bool, "object": dict, "array": list}[spec.type]
    )


def input_errors(definition: WorkflowDefinition, inputs: JsonDocument) -> list[str]:
    """Return located missing, unknown, and incorrectly typed workflow input errors."""
    errors = [
        f"{definition.id}:inputs.{name}: unknown input"
        for name in inputs.root
        if name not in definition.inputs
    ]
    for name, spec in definition.inputs.items():
        value = inputs.root.get(name, spec.default)
        if value is None and spec.required:
            errors.append(f"{definition.id}:inputs.{name}: required input is missing")
        elif value is not None and not _type_matches(spec, value):
            errors.append(f"{definition.id}:inputs.{name}: expected {spec.type}")
    return errors


def validate_inputs(definition: WorkflowDefinition, inputs: JsonDocument) -> JsonDocument:
    """Apply declared defaults and reject unknown keys before starting a run."""
    errors = input_errors(definition, inputs)
    if errors:
        raise ValidationError("; ".join(errors))
    return JsonDocument(
        {name: inputs.root.get(name, spec.default) for name, spec in definition.inputs.items()}
    )


def validate_workflow(path: Path, inputs: JsonDocument | None = None) -> list[str]:
    """Collect schema, control-flow, policy, reference, and optional input errors."""
    definition, errors = _read(path)
    if definition is not None:
        errors.extend(validate_definition(definition, path.name))
        if inputs is not None:
            errors.extend(f"{path.name}:{error}" for error in input_errors(definition, inputs))
    return errors


def load_workflow(path: Path) -> WorkflowDefinition:
    """Load one fully checked definition or raise a located domain validation error."""
    definition, errors = _read(path)
    if definition is not None:
        errors.extend(validate_definition(definition, path.name))
    if errors or definition is None:
        raise ValidationError("; ".join(errors))
    return definition


def list_workflows(path: Path | None = None) -> list[WorkflowDefinition]:
    """List all bundled workflows in stable filename order."""
    return [load_workflow(item) for item in sorted((path or workflows_path()).glob("*.yaml"))]


def get_workflow(identity: str) -> WorkflowDefinition:
    """Resolve a registered identifier without treating untrusted input as a file path."""
    for definition in list_workflows():
        if definition.id == identity:
            return definition
    msg = f"Unknown workflow: {identity}"
    raise NotFoundError(msg)
