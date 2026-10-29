# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build a versioned interface catalog without persisting duplicate object facts."""

from pydantic import BaseModel

from datakeel.core.models import JsonDocument
from datakeel.core.object_kinds import (
    object_property_model,
    register_object_kind,
    registered_object_kinds,
)
from datakeel.ontology.functions import function_definitions
from datakeel.ontology.models import (
    ActionType,
    IdentityMapping,
    LinkType,
    ObjectKind,
    ObjectType,
    OntologyRegistry,
)
from datakeel.ontology.production_links import (
    CONTAINMENT_DOMAINS,
    CONTAINMENT_RANGES,
    production_links,
)
from datakeel.ontology.properties import (
    DatasetProperties,
    FileProperties,
    TaskProperties,
    VersionProperties,
)

for _kind, _model in (
    ("dataset", DatasetProperties),
    ("version", VersionProperties),
    ("file", FileProperties),
    ("artifact", FileProperties),
    ("task", TaskProperties),
):
    register_object_kind(_kind, _model)


def object_definitions() -> list[ObjectType]:
    """Map registered fact kinds to versioned property schemas."""
    return [
        ObjectType(
            id=kind,
            properties=JsonDocument.model_validate(model.model_json_schema()),
            identity_mapping=IdentityMapping(
                asset_type=kind,
                version_field=_version_field(kind),
            ),
            description=f"Projection of authoritative {kind} facts; AssetRef is the sole identity.",
        )
        for kind in registered_object_kinds()
        if (model := object_property_model(kind)) is not None
    ]


def _version_field(kind: str) -> str | None:
    if kind in {"version", "file", "artifact"}:
        return "version_id"
    if kind == "label_set":
        return "version"
    return "revision" if kind in {"template", "model"} else None


def link_definitions() -> list[LinkType]:
    """Distinguish actual derivation from containment and semantic associations."""
    assets: list[ObjectKind] = list(registered_object_kinds())
    return [
        LinkType(
            id="derived",
            domain=assets,
            range=assets,
            cardinality="many-to-many",
            semantics="derived",
            description="A recorded transformation produced the target from the source.",
        ),
        LinkType(
            id="contains",
            domain=CONTAINMENT_DOMAINS,
            range=CONTAINMENT_RANGES,
            cardinality="one-to-many",
            semantics="contains",
            description="A manifest or dataset includes the target; inclusion is not derivation.",
        ),
        LinkType(
            id="similar_to",
            domain=["file", "artifact"],
            range=["file", "artifact"],
            cardinality="many-to-many",
            semantics="similar_to",
            description=(
                "Similarity evidence relates two assets without claiming "
                "common identity or derivation."
            ),
        ),
        LinkType(
            id="mentions",
            domain=["file", "artifact"],
            range=assets,
            cardinality="many-to-many",
            semantics="mentions",
            description="Content refers to another asset without asserting derivation.",
        ),
        *metadata_links(),
        *production_links(),
    ]


def metadata_links() -> list[LinkType]:
    """Declare directional semantic references used by catalog impact queries."""
    definitions = [
        ("measures", ["metric"], ["column"]),
        ("sliced_by", ["metric"], ["dimension"]),
        ("means", ["term"], ["metric", "dimension", "column"]),
        ("owned_by", ["table", "metric"], ["owner"]),
        ("references", ["column"], ["column"]),
    ]
    return [
        LinkType(
            id=kind,
            domain=domain,
            range=target,
            cardinality="many-to-many",
            semantics=kind,
            description=f"Catalog {kind} relationship.",
        )
        for kind, domain, target in definitions
    ]


def register_object_type(kind: str, model: type[BaseModel]) -> None:
    """Extend validated object kinds together with their public property schema."""
    register_object_kind(kind, model)


def registry(actions: list[ActionType] | None = None) -> OntologyRegistry:
    """Compose object, relationship, read-function, and controlled-action definitions."""
    return OntologyRegistry(
        object_types=object_definitions(),
        link_types=link_definitions(),
        functions=function_definitions(),
        actions=actions or [],
    )
