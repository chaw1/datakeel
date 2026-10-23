# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise located workflow rejection and actual built-in contract schemas."""

from pathlib import Path

import pytest
import yaml
from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.workflows.loader import (
    get_workflow,
    input_errors,
    list_workflows,
    load_workflow,
    validate_inputs,
    validate_workflow,
    workflows_path,
)
from datakeel.workflows.models import WorkflowDefinition
from datakeel.workflows.validation import validate_definition


def definition(steps: list[JsonValue]) -> WorkflowDefinition:
    """Create a minimal, real schema-validated graph for isolated failure cases."""
    return WorkflowDefinition.model_validate(
        {
            "id": "example",
            "name": "Example",
            "description": "Validation fixture",
            "inputs": {"dataset_id": {"type": "string"}},
            "triggers": {"keywords": [["example"]]},
            "entry": "first",
            "steps": steps,
        }
    )


def tool(name: str = "list_datasets", arguments: JsonValue = None) -> dict[str, JsonValue]:
    """Declare one read node followed by a result node."""
    return {
        "id": "first",
        "type": "tool",
        "tool": name,
        "arguments": arguments or {},
        "next": "last",
    }


def output(value: JsonValue = "done") -> dict[str, JsonValue]:
    """Create one terminal output template."""
    return {"id": "last", "type": "output", "value": value}


def write_definition(tmp_path: Path, value: WorkflowDefinition) -> Path:
    """Serialize through the public boundary instead of fabricating parsed internals."""
    path = tmp_path / "workflow.yaml"
    path.write_text(yaml.safe_dump(value.model_dump(mode="json")))
    return path


def test_builtins_load_and_metric_change_preserves_correct_order() -> None:
    """Use real registered schemas and preserve pre-change answer and impact ordering."""
    workflows = list_workflows()
    assert [item.id for item in workflows] == [
        "dataset-health",
        "low-quality-cleanup",
        "metric-change",
    ]
    metric = get_workflow("metric-change")
    assert [step.id for step in metric.steps] == [
        "current",
        "before",
        "impact",
        "update",
        "after",
        "comparison",
    ]
    assert all(step.type != "approval" for step in metric.steps)
    assert validate_inputs(metric, JsonDocument({})).root["metric_id"] == "retail_revenue"


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("unregistered", {}, "unknown tool: unregistered"),
        ("get_quality", {}, "arguments.dataset_id: Field required"),
        (
            "get_quality",
            {"dataset_id": "x", "extra": 1},
            "arguments.extra: Extra inputs are not permitted",
        ),
        ("delete_files", {"selection": {}}, "irreversible action requires an approval step"),
    ],
)
def test_invalid_tools_return_located_errors(name: str, arguments: JsonValue, message: str) -> None:
    """Unknown functions, missing parameters, extras, and unsafe policy fail at load time."""
    assert validate_definition(definition([tool(name, arguments), output()]), "bad.yaml") == [
        f"bad.yaml:steps[first]: {message}"
    ]


def test_cycles_return_located_errors() -> None:
    """Keep the mutation anchor assertion-based so removing cycle detection is killed."""
    value = definition([tool(), {**tool(), "id": "last", "next": "first"}])
    assert validate_definition(value, "cycle.yaml") == ["cycle.yaml:steps[first]: cycle detected"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("${inputs.absent}", "unknown input: absent"),
        ("${steps.absent.data}", "unknown step: absent"),
        ("${steps.last}", "reference must name an earlier step on every path: last"),
        ("${steps.first.data.absent}", "unknown output reference: steps.first.data.absent"),
        ("${arbitrary.code}", "malformed reference"),
        ({"$eval": ["1+1", 2]}, "unknown output function"),
    ],
)
def test_invalid_references_return_located_errors(value: JsonValue, message: str) -> None:
    """Reject unknown inputs, missing steps, unavailable outputs, and expression code."""
    workflow = definition(
        [tool("get_quality", {"dataset_id": "${inputs.dataset_id}"}), output(value)]
    )
    assert validate_definition(workflow, "bad.yaml") == [f"bad.yaml:steps[last]: {message}"]


def test_approval_rejects_reversible_action() -> None:
    """Human approval is reserved for declared irreversible actions."""
    step: JsonValue = {
        "id": "first",
        "type": "approval",
        "action": "quarantine_files",
        "arguments": {"selection": {}},
        "next": "last",
    }
    assert validate_definition(definition([step, output()]), "approval.yaml") == [
        "approval.yaml:steps[first]: approval requires an irreversible action"
    ]


def test_schema_errors_include_file_step_and_operator(tmp_path: Path) -> None:
    """The CLI receives the same precise Pydantic location for unsupported branch operators."""
    path = write_definition(tmp_path, definition([tool(), output()]))
    text = path.read_text().replace("type: tool", "type: unsupported")
    path.write_text(text)
    assert "workflow.yaml:steps.0:" in validate_workflow(path)[0]
    path.write_text(
        yaml.safe_dump(
            {
                **definition([tool(), output()]).model_dump(mode="json"),
                "steps": [
                    {
                        "id": "first",
                        "type": "branch",
                        "ref": "${inputs.dataset_id}",
                        "op": "eval",
                        "value": "x",
                        "then": "last",
                        "otherwise": "last",
                    },
                    output(),
                ],
            }
        )
    )
    assert "workflow.yaml:steps.0.branch.op:" in validate_workflow(path)[0]


def test_missing_inputs_return_file_and_input_location(tmp_path: Path) -> None:
    """Required values are rejected before a graph can start."""
    path = write_definition(tmp_path, definition([tool(), output()]))
    assert validate_workflow(path, JsonDocument({})) == [
        "workflow.yaml:example:inputs.dataset_id: required input is missing"
    ]
    with pytest.raises(ValidationError, match="required input"):
        validate_inputs(load_workflow(path), JsonDocument({}))


def test_invalid_files_and_unregistered_workflows_fail_closed(tmp_path: Path) -> None:
    """Neither malformed documents nor unknown identities fall back to another workflow."""
    path = tmp_path / "bad.yaml"
    path.write_text("unterminated: [")
    assert validate_workflow(path)[0].startswith("bad.yaml:document:")
    with pytest.raises(ValidationError, match=r"bad\.yaml"):
        load_workflow(path)
    assert validate_workflow(tmp_path / "missing.yaml")[0].startswith("missing.yaml:document:")
    with pytest.raises(NotFoundError, match="Unknown workflow"):
        get_workflow("../../not-a-workflow")


def test_control_edges_and_duplicate_step_ids_are_rejected() -> None:
    """Report malformed graph identities before compilation."""
    workflow = definition([tool(), output()])
    broken = workflow.model_copy(
        update={"entry": "missing", "steps": [workflow.steps[0], workflow.steps[0]]}
    )
    assert validate_definition(broken, "graph.yaml") == [
        "graph.yaml:steps: duplicate step id",
        "graph.yaml:entry: unknown step: missing",
        "graph.yaml:steps[first]: unknown next step: last",
        "graph.yaml:steps[first]: unknown next step: last",
    ]


def test_references_must_be_available_on_every_branch() -> None:
    """A branch-only predecessor cannot be referenced after a control-flow join."""
    branch: JsonValue = {
        "id": "first",
        "type": "branch",
        "ref": "${inputs.dataset_id}",
        "op": "eq",
        "value": "x",
        "then": "optional",
        "otherwise": "last",
    }
    optional: JsonValue = {**tool(), "id": "optional"}
    workflow = definition([branch, optional, output("${steps.optional.data}")])
    assert validate_definition(workflow, "join.yaml") == [
        "join.yaml:steps[last]: reference must name an earlier step on every path: optional"
    ]


def test_branch_requires_a_complete_reference() -> None:
    """Branch operands cannot smuggle a free-form expression into control flow."""
    step: JsonValue = {
        "id": "first",
        "type": "branch",
        "ref": "input + 1",
        "op": "eq",
        "value": "x",
        "then": "last",
        "otherwise": "last",
    }
    assert validate_definition(definition([step, output()]), "branch.yaml") == [
        "branch.yaml:steps[first]: branch ref must be a complete reference"
    ]


def test_input_types_defaults_and_unknown_values() -> None:
    """Boolean values are distinct from numeric inputs and defaults preserve JSON types."""
    workflow = WorkflowDefinition.model_validate(
        {
            **definition([tool(), output()]).model_dump(mode="json"),
            "inputs": {
                "count": {"type": "integer", "default": 2},
                "enabled": {"type": "boolean", "default": False},
                "optional": {"type": "string", "required": False},
                "settings": {"type": "object", "default": {}},
                "items": {"type": "array", "default": []},
                "ratio": {"type": "number", "default": 0.5},
            },
        }
    )
    assert validate_inputs(workflow, JsonDocument({})).root == {
        "count": 2,
        "enabled": False,
        "optional": None,
        "settings": {},
        "items": [],
        "ratio": 0.5,
    }
    assert input_errors(workflow, JsonDocument({"count": True, "unknown": 1})) == [
        "example:inputs.unknown: unknown input",
        "example:inputs.count: expected integer",
    ]
    assert workflows_path().name == "workflows"
