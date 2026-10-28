# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate graph topology and compatible slots before producing artifacts."""

from typing import Any

from datakeel.core.custom_operators import custom_reference
from datakeel.core.errors import ValidationError
from datakeel.operators import REGISTRY
from datakeel.pipeline.models import ConditionParams, Node, Pipeline


def reference(value: str) -> tuple[str, str]:
    """Split a fully qualified node slot."""
    if "." not in value:
        msg = f"Slot reference must be node.slot: {value}"
        raise ValidationError(msg)
    source, slot = value.split(".", 1)
    return source, slot


def _slots(node: Node) -> tuple[dict[str, str], dict[str, str]]:
    if node.kind == "operator":
        if node.operator is not None and node.operator.startswith("custom."):
            custom_reference(node.operator)
            return {"files": "files.any"}, {"files": "files.any"}
        if node.operator not in REGISTRY:
            msg = f"Unknown operator: {node.operator}"
            raise ValidationError(msg)
        operator = REGISTRY[node.operator]
        operator.params_type.model_validate(node.params)
        return dict(operator.manifest.inputs), dict(operator.manifest.outputs)
    if node.operator is not None:
        msg = "Control nodes cannot specify an operator"
        raise ValidationError(msg)
    if node.kind == "condition":
        ConditionParams.model_validate(node.params)
        return {"files": "files.any"}, {"true": "files.any", "false": "files.any"}
    if node.params:
        msg = "Route nodes have no parameters"
        raise ValidationError(msg)
    return {"files": "files.any"}, {
        "image": "files.image",
        "text": "files.text",
        "table": "files.table",
        "audio": "files.audio",
        "video": "files.video",
        "other": "files.any",
    }


def _layers(nodes: dict[str, Node]) -> list[list[Node]]:
    dependencies: dict[str, set[str]] = {}
    for node in nodes.values():
        dependencies[node.id] = set()
        for value in node.inputs.values():
            source, _ = reference(value)
            if source != "$input":
                if source not in nodes:
                    msg = f"Unknown source node: {source}"
                    raise ValidationError(msg)
                dependencies[node.id].add(source)
    layers: list[list[Node]] = []
    completed: set[str] = set()
    while dependencies:
        ready = [key for key, value in dependencies.items() if value <= completed]
        if not ready:
            msg = "Pipeline contains a cycle"
            raise ValidationError(msg)
        layers.append([nodes[key] for key in ready])
        completed.update(ready)
        for key in ready:
            del dependencies[key]
    return layers


def _validate_edges(
    layers: list[list[Node]],
    slots: dict[str, dict[str, str]],
    destinations: dict[str, dict[str, str]],
) -> None:
    for layer in layers:
        for node in layer:
            for destination, value in node.inputs.items():
                source, source_slot = reference(value)
                if source_slot not in slots[source]:
                    msg = f"Unknown output slot: {value}"
                    raise ValidationError(msg)
                slot_type = slots[source][source_slot]
                expected = destinations[node.id][destination]
                if expected not in {"files.any", slot_type}:
                    msg = (
                        f"Incompatible slot types: {value} ({slot_type}) -> {node.id}.{destination}"
                    )
                    raise ValidationError(msg)
                if node.kind == "condition":
                    slots[node.id] = {"true": slot_type, "false": slot_type}


def validate_pipeline(definition: Pipeline | dict[str, Any]) -> tuple[Pipeline, list[list[Node]]]:
    """Validate a legacy JSON or typed DAG without writing any artifacts."""
    pipeline = Pipeline.model_validate(definition)
    nodes = {node.id: node for node in pipeline.nodes}
    if len(nodes) != len(pipeline.nodes):
        msg = "Node IDs must be unique"
        raise ValidationError(msg)
    slots: dict[str, dict[str, str]] = {"$input": {"files": "files.any"}}
    destinations: dict[str, dict[str, str]] = {}
    for node in pipeline.nodes:
        destinations[node.id], slots[node.id] = _slots(node)
        if set(node.inputs) != set(destinations[node.id]):
            msg = f"Input slots for {node.id} must be {list(destinations[node.id])}"
            raise ValidationError(msg)
    layers = _layers(nodes)
    _validate_edges(layers, slots, destinations)
    for value in pipeline.outputs:
        source, slot = reference(value)
        if source not in slots or slot not in slots[source]:
            msg = f"Invalid pipeline output: {value}"
            raise ValidationError(msg)
    return pipeline, layers
