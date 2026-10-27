# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve native reads to every underlying protected asset without external I/O."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.data_asset_events import data_dependency_events
from datakeel.storage.data_asset_native import native_targets
from datakeel.storage.database import DatasetRow


def ref_key(ref: AssetRef) -> tuple[str, str, str, str | None]:
    """Compare resource identities independently of display labels."""
    return ref.asset_type, ref.asset_id, ref.namespace, ref.version


def same_resource(policy: AssetRef, actual: AssetRef) -> bool:
    """Conservatively match unversioned reads against all version-specific policies."""
    return ref_key(policy)[:3] == ref_key(actual)[:3] and (
        policy.version is None or actual.version is None or policy.version == actual.version
    )


def _adjacency(snapshot: CatalogSnapshot) -> dict[str, list[AssetRef]]:
    result: dict[str, list[AssetRef]] = {}
    objects = {item.asset_ref.asset_id: item for item in snapshot.objects}
    for item in snapshot.objects:
        if item.table_id and item.table_id in objects:
            result.setdefault(item.asset_ref.asset_id, []).append(objects[item.table_id].asset_ref)
    for link in snapshot.links:
        if link.kind == "contains" and link.source.asset_type == "table":
            result.setdefault(link.source.asset_id, []).append(link.target)
        if link.kind in {"measures", "sliced_by", "means"}:
            result.setdefault(link.source.asset_id, []).append(link.target)
        elif link.kind == "derived" or (
            link.kind == "contains" and link.source.asset_type == "table"
        ):
            result.setdefault(link.target.asset_id, []).append(link.source)
    return result


def _dataset_parents(
    session: Session,
    snapshot: CatalogSnapshot,
) -> dict[str, tuple[AssetRef, ...]]:
    dataset_rows = list(session.scalars(select(DatasetRow)))
    datasets = {row.id for row in dataset_rows}
    source_datasets: dict[str, set[str]] = {}
    for row in dataset_rows:
        source_id = row.metadata_values.get("source_id")
        if isinstance(source_id, str):
            source_datasets.setdefault(source_id, set()).add(row.id)
    objects = {item.asset_ref.asset_id: item for item in snapshot.objects}
    result: dict[str, tuple[AssetRef, ...]] = {}
    for item in snapshot.objects:
        candidates = {item.source_id or "", item.asset_ref.asset_id}
        declared = item.properties.root.get("dataset_id")
        if isinstance(declared, str):
            candidates.add(declared)
        source = objects.get(item.source_id or "")
        if source:
            declared = source.properties.root.get("dataset_id")
            if isinstance(declared, str):
                candidates.add(declared)
        candidates.update(source_datasets.get(item.source_id or "", ()))
        result[item.asset_ref.asset_id] = tuple(
            AssetRef(asset_id=identity) for identity in sorted(candidates & datasets)
        )
    for link in snapshot.links:
        if link.kind == "contains" and link.source.asset_type == "dataset":
            result[link.target.asset_id] = (*result.get(link.target.asset_id, ()), link.source)
    return result


@dataclass(frozen=True)
class TargetIndex:
    """One transaction's catalog and lineage graph, reused when resolving many reads."""

    snapshot: CatalogSnapshot
    adjacency: dict[str, list[AssetRef]]
    parents: dict[str, tuple[AssetRef, ...]]
    events: list[LineageEvent]


def target_index(session: Session) -> TargetIndex:
    """Read the catalog and data-flow events once for a batch of access checks."""
    snapshot = read_snapshot(session)
    return TargetIndex(
        snapshot=snapshot,
        adjacency=_adjacency(snapshot),
        parents=_dataset_parents(session, snapshot),
        events=data_dependency_events(session),
    )


def resolve_access_targets(
    session: Session, refs: tuple[AssetRef, ...], index: TargetIndex | None = None
) -> tuple[AssetRef, ...]:
    """Expand metrics, fields, derived outputs and table ownership to native resources."""
    current = index or target_index(session)
    snapshot, adjacency, parents = current.snapshot, current.adjacency, current.parents
    direct_datasets = {
        ref.asset_id
        for ref in refs
        if ref.asset_type in {"dataset", "resource"} and session.get(DatasetRow, ref.asset_id)
    }
    queue = list(refs)
    queue.extend(
        item.asset_ref
        for item in snapshot.objects
        if item.asset_ref.asset_type in {"table", "column"}
        and any(parent.asset_id in direct_datasets for parent in parents[item.asset_ref.asset_id])
    )
    events = current.events
    catalog = {item.asset_ref.asset_id: item.asset_ref for item in snapshot.objects}
    found: dict[tuple[str, str, str, str | None], AssetRef] = {}
    while queue:
        ref = queue.pop()
        key = ref_key(ref)
        if key in found:
            continue
        found[key] = ref
        if ref.asset_type in {"resource", "dataset"} and ref.asset_id in catalog:
            queue.append(catalog[ref.asset_id].model_copy(update={"version": ref.version}))
        queue.extend(native_targets(session, ref))
        queue.extend(adjacency.get(ref.asset_id, ()))
        for event in events:
            if (ref.asset_type == "event" and ref.asset_id == event.event_id) or any(
                same_resource(output, ref) for output in event.outputs
            ):
                queue.extend(event.inputs)
    for ref in tuple(found.values()):
        for parent in parents.get(ref.asset_id, ()):
            found[ref_key(parent)] = parent
    return tuple(found[key] for key in sorted(found, key=str))
