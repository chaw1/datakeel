# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic k1.v1 owner overlay; legacy facts remain explicitly opaque."""

from typing import Literal

from pydantic import TypeAdapter

from datakeel.actions.authorization import authorization_for
from datakeel.actions.declarations import (
    ActionHandlerSet,
    ApprovalPolicy,
    AuthorizationPolicy,
    Condition,
    Effect,
    resource,
)
from datakeel.actions.file_declarations import active_declarations
from datakeel.actions.registry import POLICIES, action_definition
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.registry import object_definitions


class AssetVocabulary(BoundaryModel):
    """Separate public schema objects from reference-only identities."""

    public: tuple[str, ...]
    references: tuple[str, ...] = resource("reference_assets.json", TypeAdapter(tuple[str, ...]))


class ActionIR(BoundaryModel):
    """A portable projection; no class objects, paths or executable callables."""

    version: Literal["k1.v1"] = "k1.v1"
    id: str
    owner: Literal["generated", "legacy"]
    legacy_projection: bool
    definition: JsonDocument
    execution_target: Literal["data_plane", "control_plane", "external"]
    authorization: AuthorizationPolicy
    approval: ApprovalPolicy | None = None
    semantics: Literal["structured", "opaque"]
    preconditions: tuple[Condition, ...] = ()
    effects: tuple[Effect, ...] = ()
    handlers: ActionHandlerSet | None = None
    surfaces: tuple[str, ...] = ()
    widget: Literal["generic", "opaque"] = "opaque"
    fixtures: tuple[str, ...] = ()
    examples: tuple[JsonDocument, ...] = ()
    source: Literal["declaration", "POLICIES"]


def vocabulary() -> AssetVocabulary:
    """Use the existing public registry without expanding its schema count."""
    return AssetVocabulary(public=tuple(item.id for item in object_definitions()))


def action_ir() -> tuple[ActionIR, ...]:
    """Replace owners at the original POLICIES positions; only probe IDs append."""
    targets = resource(
        "execution_targets.json",
        TypeAdapter(dict[str, Literal["data_plane", "control_plane", "external"]]),
    )
    declarations = active_declarations()
    result: list[ActionIR] = []
    for name in dict.fromkeys((*POLICIES, *declarations)):
        declaration = declarations.get(name)
        definition = action_definition(name)
        shared = (
            declaration.model_dump(
                include=set(ActionIR.model_fields) & set(type(declaration).model_fields),
                serialize_as_any=True,
            )
            if declaration
            else {}
        )
        result.append(
            ActionIR.model_validate(
                {
                    **shared,
                    "id": name,
                    "owner": "generated" if declaration else "legacy",
                    "legacy_projection": declaration is None,
                    "definition": definition.model_dump(mode="json"),
                    "execution_target": declaration.execution_target
                    if declaration
                    else targets[name],
                    "authorization": authorization_for(name),
                    "semantics": "structured" if declaration else "opaque",
                    "source": "declaration" if declaration else "POLICIES",
                }
            )
        )
    return tuple(result)


def file_assignments(items: tuple[ActionIR, ...]) -> tuple[Effect, ...]:
    """Consume versioned state assignments without branching on action IDs."""
    return tuple(
        effect for item in items if item.semantics == "structured" for effect in item.effects
    )
