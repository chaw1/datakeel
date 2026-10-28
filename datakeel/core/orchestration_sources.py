# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Attribute orchestration datasets to the catalog source that physically holds them."""

from collections.abc import Iterable, Sequence
from urllib.parse import unquote, urlsplit

from datakeel.core.orchestration import (
    OpenLineageDataset,
    OpenLineageNamespace,
    normalized_namespace,
)
from datakeel.core.orchestration_catalog import ResolvedDataset, resolve_dataset

UNMATCHED_SOURCE_ID = "airflow"
SourceNamespace = tuple[str, OpenLineageNamespace]


def source_namespace(source_id: str, connection_url: str) -> SourceNamespace | None:
    """Name a source's server and database as OpenLineage does, without its credentials.

    Only URLs naming a host and a database qualify; a file database or a server-level
    connection cannot prove which dataset it holds.
    """
    try:
        parts = urlsplit(connection_url)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    database = unquote(parts.path.strip("/").split("/", 1)[0])
    if not parts.scheme or not host or not database:
        return None
    authority = f"[{host}]" if ":" in host else host
    scheme = parts.scheme.split("+", 1)[0]
    namespace = normalized_namespace(f"{scheme}://{authority}{f':{port}' if port else ''}")
    return namespace, OpenLineageNamespace(source_id=source_id, database=database)


def known_sources(
    mappings: dict[str, OpenLineageNamespace], connections: Iterable[tuple[str, str]]
) -> tuple[SourceNamespace, ...]:
    """Explicit namespace mappings first, then catalog sources whose connection names them."""
    explicit = [(normalized_namespace(key), value) for key, value in mappings.items()]
    inferred = [
        value
        for source_id, url in connections
        if (value := source_namespace(source_id, url)) is not None
    ]
    return (*explicit, *inferred)


def attribute_dataset(
    dataset: OpenLineageDataset, sources: Sequence[SourceNamespace]
) -> ResolvedDataset:
    """Match a known source by namespace and database, else file under the placeholder.

    Unmatched datasets keep their namespace and database in the placeholder schema
    segment, so equally named tables on different servers never merge.
    """
    for namespace, source in sources:
        if namespace == dataset.namespace:
            resolved = resolve_dataset(dataset, {namespace: source})
            if resolved.source_id == source.source_id:
                return resolved
    relation = resolve_dataset(dataset, {}).relation
    qualifier = ".".join(
        part for part in (relation.database, relation.schema_name) if part and part != "default"
    )
    location = f"{dataset.namespace}/{qualifier}" if qualifier else dataset.namespace
    return ResolvedDataset(source_id=UNMATCHED_SOURCE_ID, relation=relation, location=location)
