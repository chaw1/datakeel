# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import versioned dbt artifacts as catalog metadata without executing project code."""

import hashlib
import re

from pydantic import JsonValue
from pydantic import ValidationError as SchemaError
from sqlglot.dialects.dialect import Dialect

from datakeel.catalog.importers.dbt_models import (
    DbtCatalog,
    DbtCatalogNode,
    DbtManifest,
    DbtNode,
    DbtUnitTest,
    stable_resource,
)
from datakeel.catalog.importers.dbt_objects import (
    integrated_object,
    merge_dbt_objects,
    owner_objects,
    resource_metadata,
    resource_table,
)
from datakeel.catalog.importers.dbt_retention import (
    catalog_evidence,
    retained_catalog,
    retained_columns,
    retention_note,
)
from datakeel.catalog.importers.dbt_runs import run_outcome, run_record, run_results
from datakeel.catalog.importers.dbt_semantics import metric_drafts
from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.catalog.importers.models import SqlDefinition
from datakeel.catalog.importers.sql import derive_sql
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    SourceProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import DbtImportRequest, MetadataImportBatch
from datakeel.core.models import AssetRef, JsonDocument

_MANIFEST_VERSION = re.compile(r"https://schemas\.getdbt\.com/dbt/manifest/v(10|11|12)\.json")
_TABLE_TYPES = frozenset({"model", "source", "seed", "snapshot"})
_ADAPTER_DIALECTS = {"sqlserver": "tsql", "synapse": "tsql", "glue": "spark"}


def sql_dialect(adapter_type: str | None) -> str:
    """Map a dbt adapter name to a parser dialect; unknown adapters use generic SQL."""
    if not adapter_type:
        return ""
    name = adapter_type.casefold()
    name = _ADAPTER_DIALECTS.get(name, name)
    try:
        Dialect.get_or_raise(name)
    except ValueError:
        return ""
    return name


def _validate_manifest(document: JsonDocument) -> DbtManifest:
    metadata = document.root.get("metadata")
    version = metadata.get("dbt_schema_version") if isinstance(metadata, dict) else None
    if not isinstance(version, str) or not _MANIFEST_VERSION.fullmatch(version):
        msg = "Unsupported dbt manifest version; supported schema versions are v10, v11, v12"
        raise ValidationError(msg)
    try:
        return DbtManifest.model_validate(document.root)
    except SchemaError as error:
        msg = f"Invalid dbt manifest resource: {error.errors(include_input=False)[0]['loc']}"
        raise ValidationError(msg) from error


def _collection(document: JsonDocument, name: str) -> dict[str, JsonDocument]:
    value = document.root.get(name, {})
    if not isinstance(value, dict):
        msg = f"dbt artifact {name} must be an object"
        raise ValidationError(msg)
    return {key: stable_resource(JsonDocument.model_validate(item)) for key, item in value.items()}


def _tests_by_parent(manifest: DbtManifest) -> dict[str, list[DbtNode | DbtUnitTest]]:
    index: dict[str, list[DbtNode | DbtUnitTest]] = {}
    for test in (*manifest.nodes.values(), *manifest.unit_tests.values()):
        if test.resource_type in {"test", "unit_test"}:
            for parent in dict.fromkeys(test.depends_on.nodes):
                index.setdefault(parent, []).append(test)
    return index


def _evidence(
    node: DbtNode,
    tests_by_parent: dict[str, list[DbtNode | DbtUnitTest]],
    raw_nodes: dict[str, JsonDocument],
    results: dict[str, JsonDocument],
    reflected: DbtCatalogNode | None,
) -> JsonDocument:
    tests: list[JsonValue] = []
    for test in tests_by_parent.get(node.unique_id, ()):
        evidence: dict[str, JsonValue] = {
            "unique_id": test.unique_id,
            "definition": raw_nodes[test.unique_id].root,
        }
        if test.unique_id in results:
            evidence["result"] = run_outcome(results[test.unique_id]).root
        tests.append(evidence)
    code = node.compiled_code or node.compiled_sql
    details: dict[str, JsonValue] = {
        "resource_type": node.resource_type,
        "tests": tests,
        "compiled_sql_hash": hashlib.sha256(code.encode()).hexdigest()
        if code is not None
        else None,
        "materialized": node.config.materialized,
    }
    if node.unique_id in results:
        details["run_result"] = run_outcome(results[node.unique_id]).root
    if reflected is not None:
        details["catalog"] = catalog_evidence(reflected)
    return JsonDocument(details)


def _exposure(source_id: str, node: DbtNode) -> CatalogObject:
    item = CatalogObject(
        asset_ref=AssetRef(
            asset_type="exposure",
            asset_id=catalog_id(source_id, "dbt-exposure", node.unique_id),
            display_name=node.name,
        ),
        name=node.name,
        source_id=source_id,
    )
    return integrated_object(
        item, resource_metadata(node, JsonDocument({"resource_type": "exposure"}))
    )


def _resource_links(
    nodes: tuple[DbtNode, ...], resources: dict[str, CatalogObject]
) -> tuple[CatalogLink, ...]:
    links: list[CatalogLink] = []
    for node in nodes:
        target = resources.get(node.unique_id)
        if target is None:
            continue
        links.extend(
            CatalogLink(source=resources[parent].asset_ref, target=target.asset_ref, kind="derived")
            for parent in node.depends_on.nodes
            if parent in resources
        )
    return tuple(links)


def _catalog(
    request: DbtImportRequest, previous: CatalogSnapshot | None
) -> dict[str, DbtCatalogNode]:
    if request.catalog is None:
        return retained_catalog(previous)
    catalog = DbtCatalog.model_validate(request.catalog.root)
    return {**catalog.nodes, **catalog.sources}


def _reflect(
    request: DbtImportRequest, manifest: DbtManifest, reflected: dict[str, DbtCatalogNode]
) -> MetadataImportBatch:
    results = run_results(request.run_results)
    raw_nodes = {
        **_collection(request.manifest, "nodes"),
        **_collection(request.manifest, "unit_tests"),
    }
    tests = _tests_by_parent(manifest)
    dialect = sql_dialect(manifest.metadata.adapter_type)
    source = metadata_object(
        "source",
        catalog_id(request.source_id),
        request.name,
        SourceProperties(dialect=manifest.metadata.adapter_type or "unknown"),
    )
    objects = [source]
    links: list[CatalogLink] = []
    sql: list[SqlDefinition] = []
    resources: dict[str, CatalogObject] = {}
    nodes = (*manifest.nodes.values(), *manifest.sources.values(), *manifest.exposures.values())
    for node in nodes:
        if node.resource_type not in _TABLE_TYPES | {"exposure"}:
            continue
        if node.resource_type == "exposure":
            item = _exposure(request.source_id, node)
        else:
            evidence = _evidence(node, tests, raw_nodes, results, reflected.get(node.unique_id))
            metadata = resource_metadata(node, evidence)
            batch = resource_table(
                request.source_id, node, reflected.get(node.unique_id), metadata, dialect
            )
            item = batch.table
            objects.extend(batch.columns)
            links.extend(batch.links)
        objects.append(item)
        links.append(contains(source, item))
        resources[node.unique_id] = item
        if node.resource_type in {"model", "snapshot"} and (
            code := node.compiled_code or node.compiled_sql
        ):
            sql.append(
                SqlDefinition(
                    origin=node.unique_id,
                    table_id=item.asset_ref.asset_id,
                    sql=code,
                    dialect=dialect,
                )
            )
    objects.extend(metric_drafts(request, resources))
    links.extend(_resource_links(nodes, resources))
    snapshot = _owned_snapshot(request.source_id, objects, links)
    derived = derive_sql(snapshot, tuple(sql))
    return MetadataImportBatch(
        snapshot=derived.snapshot,
        parse_failures=derived.failures,
        run_record=run_record(request.source_id, request.run_results, results),
    )


def _owned_snapshot(
    source_id: str, objects: list[CatalogObject], links: list[CatalogLink]
) -> CatalogSnapshot:
    for item in tuple(objects):
        if "integration" not in item.properties.root:
            continue
        owner = owner_objects(item)
        if owner:
            objects.append(owner[0])
            links.append(owner[1])
    unique: dict[tuple[str, str], CatalogObject] = {}
    for item in objects:
        key = (item.asset_ref.asset_type, item.asset_ref.asset_id)
        if key in unique and "integration" in item.properties.root:
            unique[key] = merge_dbt_objects(unique[key], item)
        else:
            unique[key] = item
    return CatalogSnapshot(
        scope=dbt_scope(source_id),
        objects=tuple(unique[key] for key in sorted(unique)),
        links=tuple(links),
    )


def dbt_scope(source_id: str) -> str:
    """Name the independently versioned catalog scope owned by one dbt import source."""
    return f"metadata:dbt:{source_id}"


def prepare_dbt(
    request: DbtImportRequest, previous: CatalogSnapshot | None = None
) -> MetadataImportBatch:
    """Validate supported artifacts and prepare a complete, nonexecuting import snapshot.

    Without catalog.json, ``previous`` (the scope's current version) supplies the last
    reflected columns, so omitting the artifact never reads as columns being dropped.
    """
    manifest = _validate_manifest(request.manifest)
    try:
        batch = _reflect(request, manifest, _catalog(request, previous))
    except SchemaError as error:
        msg = "Invalid dbt catalog or run-results artifact"
        raise ValidationError(msg) from error
    if request.catalog is not None:
        return batch
    count = retained_columns(batch.snapshot)
    return batch.model_copy(update={"retained_columns": count, "notes": (retention_note(count),)})
