# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read bounded column observations from already registered read-only catalog sources."""

import re

from datakeel.core.catalog_identity import catalog_id, catalog_segments
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot, SourceProperties
from datakeel.core.standard_models import ColumnProfile, Sensitivity
from datakeel.storage.standard_observations import read_observations

_SHAPE = re.compile(r"\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)")
_SENSITIVITIES: tuple[Sensitivity, ...] = ("public", "internal", "confidential", "restricted")


def _owner(snapshot: CatalogSnapshot, column: CatalogObject) -> str:
    source_asset_id = catalog_id(column.source_id) if column.source_id is not None else None
    targets = {
        link.target.asset_id
        for link in snapshot.links
        if link.kind == "owned_by"
        and link.source.asset_id in {column.asset_ref.asset_id, column.table_id, source_asset_id}
    }
    return ", ".join(
        sorted(item.name for item in snapshot.objects if item.asset_ref.asset_id in targets)
    )


def _profile(snapshot: CatalogSnapshot, column: CatalogObject) -> ColumnProfile:
    properties = column.properties.root
    data_type = str(properties.get("data_type", "unknown"))
    shape = _SHAPE.search(data_type)
    numeric = any(name in data_type.casefold() for name in ("numeric", "decimal", "number"))
    size = int(shape[1]) if shape else None
    sensitivity: Sensitivity | None = next(
        (item for item in _SENSITIVITIES if item == properties.get("sensitivity")), None
    )
    unit = properties.get("unit")
    return ColumnProfile(
        column_id=column.asset_ref.asset_id,
        name=column.name,
        data_type=data_type,
        source_id=column.source_id or "",
        table_id=column.table_id or "",
        owner=_owner(snapshot, column),
        unit=unit if isinstance(unit, str) else None,
        sensitivity=sensitivity,
        length=size if not numeric else None,
        precision=size if numeric else None,
        scale=int(shape[2]) if numeric and shape and shape[2] else None,
    )


def _observe(
    source: CatalogObject, table: CatalogObject, profiles: tuple[ColumnProfile, ...]
) -> tuple[ColumnProfile, ...]:
    properties = SourceProperties.model_validate(source.properties.root)
    if not properties.connection_url or properties.dialect not in {
        "sqlite",
        "postgres",
        "postgresql",
    }:
        return profiles
    return read_observations(properties, table, profiles)


def profiles_from_snapshot(
    snapshot: CatalogSnapshot, table_id: str | None = None
) -> tuple[ColumnProfile, ...]:
    """Profile all catalog columns, bounding each table to 10,000 actual observations."""
    sources = {
        item.source_id or catalog_segments(item.asset_ref.asset_id)[0]: item
        for item in snapshot.objects
        if item.asset_ref.asset_type == "source"
    }
    tables = {
        item.asset_ref.asset_id: item
        for item in snapshot.objects
        if item.asset_ref.asset_type == "table"
    }
    groups: dict[str, list[ColumnProfile]] = {}
    for column in snapshot.objects:
        if column.asset_ref.asset_type == "column" and (
            table_id is None or column.table_id == table_id
        ):
            groups.setdefault(column.table_id or "", []).append(_profile(snapshot, column))
    result: list[ColumnProfile] = []
    for identity, items in sorted(groups.items()):
        profiles = tuple(items)
        table = tables.get(identity)
        source = sources.get(profiles[0].source_id)
        result.extend(_observe(source, table, profiles) if source and table else profiles)
    return tuple(result)
