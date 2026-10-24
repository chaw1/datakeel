# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register knowledge graph object and predicate semantics without side storage."""

from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_product import KGEntity
from datakeel.core.object_kinds import register_object_kind
from datakeel.core.predicate_registry import Predicate, register_predicate


def register_kg_schema(schema: KGSchema) -> None:
    """Make checked schema relations available to all evidence boundary models."""
    register_object_kind("kg_entity", KGEntity)
    register_predicate(
        Predicate(
            id="kg.mentions",
            description="An entity occurs in a source document",
            object_kind="asset",
            object_asset_types=("file",),
            subject_asset_type="kg_entity",
            existence=False,
        )
    )
    register_predicate(
        Predicate(
            id="kg.same_as",
            description="A symmetric candidate alias pair without transitive inference",
            object_kind="asset",
            object_asset_types=("kg_entity",),
            subject_asset_type="kg_entity",
            existence=False,
            symmetric=True,
        )
    )
    for relation in schema.relations:
        register_predicate(
            Predicate(
                id=f"kg.{relation.name}",
                description=f"Schema-defined directed graph relation: {relation.name}",
                object_kind="asset",
                object_asset_types=("kg_entity",),
                subject_asset_type="kg_entity",
                existence=False,
            )
        )
