# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Map dbt resource identities and descriptive metadata to physical catalog objects."""

import sqlglot
from pydantic import JsonValue
from sqlglot import exp
from sqlglot.errors import SqlglotError

from datakeel.catalog.importers.dbt_models import DbtCatalogNode, DbtColumn, DbtNode
from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.core.catalog_identity import catalog_id, catalog_segments
from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    ColumnProperties,
    TableProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import ExternalMetadata, PhysicalRelation
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


class DbtObjectBatch(BoundaryModel):
    """Return a resource and its fields without exposing untyped boundary dictionaries."""

    table: CatalogObject
    columns: tuple[CatalogObject, ...]
    links: tuple[CatalogLink, ...]


def physical_relation(node: DbtNode, dialect: str) -> PhysicalRelation:
    """Prefer the warehouse relation spelling and parse quoted qualification as SQL."""
    if not node.relation_name:
        return PhysicalRelation(
            database=node.database,
            schema_name=node.schema_name,
            name=node.identifier or node.alias or node.name,
        )
    try:
        relation = sqlglot.parse_one(node.relation_name, read=dialect, into=exp.Table)
    except (SqlglotError, ValueError) as error:
        msg = f"Invalid dbt relation_name for {node.unique_id}"
        raise ValidationError(msg) from error
    if not relation.name:
        msg = f"Invalid dbt relation_name for {node.unique_id}"
        raise ValidationError(msg)
    return PhysicalRelation(
        database=relation.catalog or node.database,
        schema_name=relation.db or node.schema_name,
        name=relation.name,
    )


def resource_owner(node: DbtNode) -> str | None:
    """Resolve resource meta, configured meta, inherited source meta, then exposure owners."""
    candidates = (
        node.meta.get("owner"),
        node.config.meta.get("owner"),
        node.source_meta.get("owner"),
    )
    for owner in candidates:
        if isinstance(owner, str) and owner.strip():
            return owner
    if node.owner:
        return node.owner.name or node.owner.email
    return None


def resource_metadata(node: DbtNode, details: JsonDocument) -> ExternalMetadata:
    """Create immutable resource provenance before physical relation resolution."""
    return ExternalMetadata(
        system="dbt",
        unique_id=node.unique_id,
        description=node.description or None,
        owner=resource_owner(node),
        tags=tuple(sorted(set(node.tags) | set(node.config.tags))),
        details=details,
    )


def integrated_object(item: CatalogObject, metadata: ExternalMetadata) -> CatalogObject:
    """Add dbt provenance without changing the existing reflected property vocabulary."""
    return item.model_copy(
        update={
            "properties": JsonDocument(
                {**item.properties.root, "integration": metadata.model_dump(mode="json")}
            )
        }
    )


def _column(
    table: CatalogObject, manifest: DbtColumn | None, reflected: DbtColumn, ordinal: int
) -> CatalogObject:
    description = (manifest.description if manifest else "") or reflected.comment
    column = metadata_object(
        "column",
        catalog_id(*catalog_segments(table.asset_ref.asset_id), reflected.name),
        reflected.name,
        ColumnProperties(
            data_type=reflected.type or reflected.data_type or "UNKNOWN",
            comment=description,
            ordinal=ordinal,
        ),
    )
    metadata = ExternalMetadata.model_validate(table.properties.root["integration"])
    tags = manifest.tags if manifest else reflected.tags
    return integrated_object(
        column,
        metadata.model_copy(
            update={
                "unique_id": f"{metadata.unique_id}.{reflected.name}",
                "description": description,
                "tags": tuple(sorted(set(metadata.tags) | set(tags))),
                "details": JsonDocument(
                    {
                        "resource_type": "column",
                        "parent_resource_type": metadata.details.root.get("resource_type"),
                        "tests": _column_tests(metadata, reflected.name),
                    }
                ),
            }
        ),
    )


def _column_tests(metadata: ExternalMetadata, name: str) -> list[JsonValue]:
    tests = metadata.details.root.get("tests", [])
    if not isinstance(tests, list):
        return []
    return [
        test
        for test in tests
        if isinstance(test, dict)
        and isinstance(definition := test.get("definition"), dict)
        and definition.get("column_name") == name
    ]


def _declared_column(node: DbtNode, name: str) -> DbtColumn | None:
    exact = next((column for column in node.columns.values() if column.name == name), None)
    if exact:
        return exact
    matches = [
        column for column in node.columns.values() if column.name.casefold() == name.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


def _resource_columns(node: DbtNode, catalog: DbtCatalogNode | None) -> tuple[DbtColumn, ...]:
    reflected = list(catalog.columns.values()) if catalog else []
    for column in node.columns.values():
        if any(field.name == column.name for field in reflected):
            continue
        matches = [field for field in reflected if field.name.casefold() == column.name.casefold()]
        if len(matches) != 1 or _declared_column(node, matches[0].name) != column:
            reflected.append(column)
    return tuple(sorted(reflected, key=lambda column: column.index))


def resource_table(
    source_id: str,
    node: DbtNode,
    catalog: DbtCatalogNode | None,
    metadata: ExternalMetadata,
    dialect: str,
) -> DbtObjectBatch:
    """Merge declared descriptions with catalog field types using the physical identity."""
    relation = physical_relation(node, dialect)
    ordered = _resource_columns(node, catalog)
    table = metadata_object(
        "table",
        catalog_id(source_id, relation.schema_name, relation.name),
        relation.name,
        TableProperties(
            columns={field.name: field.type or field.data_type or "UNKNOWN" for field in ordered},
            comment=node.description or (catalog.metadata.comment if catalog else None),
            is_view=(catalog.metadata.type if catalog else node.config.materialized).casefold()
            == "view",
            sql=node.compiled_code or node.compiled_sql,
        ),
    )
    table = integrated_object(table, metadata.model_copy(update={"relation": relation}))
    columns = tuple(
        _column(table, _declared_column(node, field.name), field, index)
        for index, field in enumerate(ordered)
    )
    return DbtObjectBatch(
        table=table, columns=columns, links=tuple(contains(table, column) for column in columns)
    )


def owner_objects(item: CatalogObject) -> tuple[CatalogObject, CatalogLink] | None:
    """Build stable owner nodes and explicit ownership relationships for directory reads."""
    metadata = ExternalMetadata.model_validate(item.properties.root["integration"])
    if not metadata.owner:
        return None
    identity = catalog_id(item.source_id or "dbt", "dbt-owner", metadata.owner)
    owner = CatalogObject(
        asset_ref=AssetRef(asset_type="owner", asset_id=identity, display_name=metadata.owner),
        name=metadata.owner,
        source_id=item.source_id,
        properties=JsonDocument({"name": metadata.owner}),
    )
    return owner, CatalogLink(source=item.asset_ref, target=owner.asset_ref, kind="owned_by")


def _resource_rank(metadata: ExternalMetadata) -> tuple[int, bool, str]:
    kind = metadata.details.root.get("parent_resource_type") or metadata.details.root.get(
        "resource_type"
    )
    priorities = {"model": 4, "snapshot": 3, "source": 2, "seed": 1}
    return priorities.get(str(kind), 0), bool(metadata.description), metadata.unique_id


def _merged_properties(previous: CatalogObject, current: CatalogObject) -> JsonDocument:
    properties = dict(previous.properties.root)
    properties.update(
        {
            key: value
            for key, value in current.properties.root.items()
            if value not in (None, "UNKNOWN", "")
        }
    )
    left_columns = previous.properties.root.get("columns")
    right_columns = current.properties.root.get("columns")
    if isinstance(left_columns, dict) and isinstance(right_columns, dict):
        properties["columns"] = {
            **left_columns,
            **{key: value for key, value in right_columns.items() if value != "UNKNOWN"},
        }
    return JsonDocument(properties)


def merge_dbt_objects(previous: CatalogObject, current: CatalogObject) -> CatalogObject:
    """Coalesce source and seed declarations for the same warehouse relation or field."""
    left = ExternalMetadata.model_validate(previous.properties.root["integration"])
    right = ExternalMetadata.model_validate(current.properties.root["integration"])
    if (
        left.relation is not None
        and right.relation is not None
        and left.relation.database is not None
        and right.relation.database is not None
        and left.relation.database != right.relation.database
    ):
        msg = (
            "Conflicting dbt databases for one physical table; "
            "import each database with a separate source_id"
        )
        raise ValidationError(msg)
    if _resource_rank(left) > _resource_rank(right):
        left, right = right, left
        previous, current = current, previous
    details = {**left.details.root, **right.details.root}
    aliases = {left.unique_id, right.unique_id}
    for metadata in (left, right):
        values = metadata.details.root.get("resource_aliases", [])
        if isinstance(values, list):
            aliases.update(value for value in values if isinstance(value, str))
    details["resource_aliases"] = [*sorted(aliases)]
    tests: dict[str, JsonValue] = {}
    for metadata in (left, right):
        evidence = metadata.details.root.get("tests", [])
        if isinstance(evidence, list):
            tests.update(
                (str(test["unique_id"]), test)
                for test in evidence
                if isinstance(test, dict) and "unique_id" in test
            )
    details["tests"] = list(tests.values())
    metadata = right.model_copy(
        update={
            "description": right.description or left.description,
            "owner": right.owner or left.owner,
            "tags": tuple(sorted(set(left.tags) | set(right.tags))),
            "details": JsonDocument(details),
        }
    )
    return integrated_object(
        current.model_copy(update={"properties": _merged_properties(previous, current)}), metadata
    )
