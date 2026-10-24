# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Registry schemas describe real projections and distinct relationship meanings."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

from jsonschema import Draft202012Validator

from datakeel.core.models import JsonDocument
from datakeel.ontology.models import ActionType, ObjectSet
from datakeel.ontology.registry import registry
from datakeel.storage.object_queries import evaluate


def test_registry_when_built_exposes_all_declared_asset_and_read_function_types() -> None:
    """Verify registry when built exposes all declared asset and read function types."""
    value = registry()
    assert {item.id for item in value.object_types} == {
        "source",
        "table",
        "column",
        "metric",
        "dimension",
        "term",
        "owner",
        "dataset",
        "version",
        "file",
        "artifact",
        "task",
        "question",
        "kg_entity",
    }
    assert len(value.functions) == 13


def test_link_definitions_when_built_keep_semantics_distinct() -> None:
    """Verify link definitions when built keep semantics distinct."""
    assert {item.semantics for item in registry().link_types} == {
        "derived",
        "contains",
        "similar_to",
        "mentions",
        "measures",
        "sliced_by",
        "means",
        "owned_by",
        "references",
    }


def test_registry_when_serialized_all_schema_documents_are_valid_json_schema() -> None:
    """Verify registry when serialized all schema documents are valid json schema."""
    value = registry()
    schemas = [item.properties for item in value.object_types]
    schemas.extend(item.input_schema for item in value.functions)
    schemas.extend(item.output_schema for item in value.functions)
    for schema in schemas:
        Draft202012Validator.check_schema(schema.root)


def test_registry_when_actions_supplied_preserves_controlled_action_contract() -> None:
    """Verify registry when actions supplied preserves controlled action contract."""
    action = ActionType(
        id="quarantine_files",
        params_schema=JsonDocument({"type": "object"}),
        auth_scope="files:write",
        preconditions=["exists"],
        effects=["quarantined"],
        reversible=True,
        handler="actions.prepare",
    )
    assert registry([action]).actions == [action]


def test_object_schemas_when_applied_to_authoritative_projection_validate(
    db: Database, dataset: DatasetView
) -> None:
    """Verify object schemas when applied to authoritative projection validate."""
    definitions = {item.id: item for item in registry().object_types}
    for kind in ("dataset", "version", "file"):
        manifest = evaluate(
            db, ObjectSet.model_validate({"object_type": kind, "dataset_id": dataset.id})
        )
        validator = Draft202012Validator(definitions[kind].properties.root)
        assert manifest.objects
        for value in manifest.objects:
            validator.validate(value.properties)
