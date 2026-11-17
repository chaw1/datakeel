# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Active declarations; membership is the only migration owner switch."""

from pydantic import TypeAdapter

from datakeel.actions.declarations import (
    ActionDeclaration,
    ActionExample,
    resource,
)
from datakeel.actions.selection_parameters import SelectionParams
from datakeel.core.models import BoundaryModel, JsonDocument


class ExampleSelection(BoundaryModel):
    """Immutable example input; request defaults remain owned by the canonical schema."""

    dataset_id: str


class ExampleParams(BoundaryModel):
    """A typed example with no mutable legacy ObjectSet containers."""

    selection: ExampleSelection


def _declaration(data: JsonDocument) -> ActionDeclaration:
    value = data.root
    examples = TypeAdapter(tuple[JsonDocument, ...]).validate_python(value["examples"])
    return ActionDeclaration.model_validate(
        {
            **value,
            "params": SelectionParams,
            "examples": tuple(
                ActionExample.model_validate(
                    {**example.root, "params": ExampleParams.model_validate(example.root["params"])}
                )
                for example in examples
            ),
        }
    )


DECLARATIONS = tuple(
    _declaration(item)
    for item in resource("file_declarations.json", TypeAdapter(tuple[JsonDocument, ...]))
)


def active_declarations() -> dict[str, ActionDeclaration]:
    """Reject duplicate owners instead of silently overwriting a declaration."""
    result = {item.id: item for item in DECLARATIONS}
    if len(result) != len(DECLARATIONS):
        msg = "Duplicate action declaration owner"
        raise ValueError(msg)
    return result
