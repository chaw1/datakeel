# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Map orchestration dataset references to stable catalog identities."""

from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import ConfigDict

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import CatalogObject
from datakeel.core.metadata_imports import ExternalMetadata, PhysicalRelation
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.core.orchestration import (
    OpenLineageDataset,
    OpenLineageNamespace,
    normalized_namespace,
)

_DATABASE_PARTS = 3
_SCHEMA_PARTS = 2
# OpenLineage naming: file systems, object stores and topics name a path or topic, never
# database.schema.table. "file" and "dbfs" also appear as bare, scheme-less namespaces.
_PATH_SCHEMES = frozenset({"s3", "gs", "hdfs", "file", "abfss", "wasbs", "dbfs", "kafka"})
_PATH_NAMESPACES = frozenset({"file", "dbfs"})


class ResolvedDataset(BoundaryModel):
    """Keep explicit source identity separate from an external namespace.

    ``location`` replaces the schema segment for a dataset filed under a placeholder
    source, keeping its namespace and database in the catalog identity.
    """

    source_id: str
    relation: PhysicalRelation
    location: str | None = None


class DatasetField(BoundaryModel):
    """Read the common standard OpenLineage schema facet field attributes."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    name: str
    type: str = "unknown"
    description: str | None = None


class DatasetSchema(BoundaryModel):
    """Ignore facet attribution keys while keeping a typed field collection."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    fields: tuple[DatasetField, ...] = ()


def resolve_dataset(
    dataset: OpenLineageDataset,
    mappings: dict[str, OpenLineageNamespace],
    fallback_source_id: str | None = None,
) -> ResolvedDataset:
    """Apply opt-in source mapping; otherwise retain the normalized namespace identity."""
    mapped = next(
        (
            value
            for key, value in mappings.items()
            if normalized_namespace(key) == dataset.namespace
        ),
        None,
    )
    scheme = urlsplit(dataset.namespace).scheme
    relational = scheme not in _PATH_SCHEMES and dataset.namespace not in _PATH_NAMESPACES
    parts = dataset.name.split(".") if relational else [dataset.name]
    database = parts[-3] if len(parts) >= _DATABASE_PARTS else mapped.database if mapped else None
    schema = parts[-2] if len(parts) >= _SCHEMA_PARTS else "default"
    if mapped and mapped.database and database != mapped.database:
        mapped = None
    suffix = f":{database}" if database else ""
    source = (
        mapped.source_id
        if mapped
        else fallback_source_id or f"openlineage:{dataset.namespace}{suffix}"
    )
    return ResolvedDataset(
        source_id=source,
        relation=PhysicalRelation(
            database=database,
            schema_name=schema,
            name=parts[-1],
            namespace=dataset.namespace,
        ),
    )


def dataset_from_uri(uri: str) -> OpenLineageDataset:
    """Split offline Airflow Dataset URIs into namespace and case-preserving names."""
    parts = urlsplit(uri)
    if parts.scheme and parts.netloc:
        namespace = f"{parts.scheme}://{parts.netloc}"
        name = unquote(parts.path.lstrip("/"))
    elif parts.scheme == "file" and parts.path:
        namespace = "file"
        name = unquote(parts.path)
    else:
        namespace = "airflow-dataset"
        name = uri
    return OpenLineageDataset(namespace=namespace, name=name or uri)


def dataset_object(
    dataset: OpenLineageDataset,
    resolved: ResolvedDataset,
    system: Literal["airflow", "openlineage"],
    details: JsonDocument | None = None,
) -> CatalogObject:
    """Construct an enrichable placeholder with physical relation and raw schema evidence."""
    relation = resolved.relation
    schema = DatasetSchema.model_validate(dataset.facets.root.get("schema", {}))
    metadata = ExternalMetadata(
        system=system,
        unique_id=catalog_id(dataset.namespace, dataset.name),
        relation=relation,
        details=details or JsonDocument({"facets": dataset.facets.root, "placeholder": True}),
    )
    schema_name = resolved.location or relation.schema_name
    identity = catalog_id(resolved.source_id, schema_name, relation.name)
    return CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id=identity, display_name=relation.name),
        name=relation.name,
        source_id=resolved.source_id,
        schema_name=schema_name,
        properties=JsonDocument(
            {
                "columns": {field.name: field.type for field in schema.fields},
                "integration": metadata.model_dump(mode="json"),
            }
        ),
    )


def dataset_columns(dataset: OpenLineageDataset, table: CatalogObject) -> tuple[CatalogObject, ...]:
    """Register standard dataset schema facets as typed catalog column objects."""
    schema = DatasetSchema.model_validate(dataset.facets.root.get("schema", {}))
    return tuple(
        CatalogObject(
            asset_ref=AssetRef(
                asset_type="column",
                asset_id=catalog_id(
                    table.source_id or "", table.schema_name or "", table.name, f.name
                ),
                display_name=f.name,
            ),
            name=f.name,
            source_id=table.source_id,
            schema_name=table.schema_name,
            table_id=table.asset_ref.asset_id,
            properties=JsonDocument(
                {"data_type": f.type, "nullable": True, "comment": f.description, "ordinal": i}
            ),
        )
        for i, f in enumerate(schema.fields)
    )
