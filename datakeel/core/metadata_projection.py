# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Merge physical catalog identities while preserving independent source contributions."""

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument


def _priority(scope: str) -> int:
    if scope.startswith("source:"):
        return 0
    return 3 if ":dbt:" in scope else 2


def _properties(objects: tuple[CatalogObject, ...], physical: CatalogObject | None) -> JsonDocument:
    properties: dict[str, JsonValue] = {}
    for item in objects:
        for key, value in item.properties.root.items():
            existing = properties.get(key)
            if value in (None, "", [], {}) and existing not in (None, "", [], {}):
                continue
            properties[key] = (
                {**existing, **value}
                if key == "columns" and isinstance(existing, dict) and isinstance(value, dict)
                else value
            )
    if physical:
        properties.update(
            {
                key: value
                for key, value in physical.properties.root.items()
                if key
                in {
                    "data_type",
                    "nullable",
                    "primary_key",
                    "foreign_keys",
                    "dialect",
                    "connection_url",
                }
            }
        )
        columns = physical.properties.root.get("columns")
        if isinstance(columns, dict):
            merged = properties.get("columns")
            properties["columns"] = {**(merged if isinstance(merged, dict) else {}), **columns}
    return JsonDocument(properties)


def _merge(contributions: tuple[tuple[str, CatalogObject], ...]) -> CatalogObject:
    if len({item.asset_ref.asset_type for _, item in contributions}) != 1:
        msg = "Catalog identity already belongs to another object type"
        raise ValidationError(msg)
    if len(contributions) == 1:
        return contributions[0][1]
    ordered = sorted(contributions, key=lambda pair: (_priority(pair[0]), pair[0]))
    items = tuple(item for _, item in ordered)
    physical = next((item for scope, item in ordered if scope.startswith("source:")), None)
    properties = _properties(items, physical)
    integrations: dict[str, JsonValue] = {
        scope: item.properties.root["integration"]
        for scope, item in ordered
        if "integration" in item.properties.root
    }
    if integrations:
        properties = JsonDocument(
            {
                **properties.root,
                "integrations": integrations,
                "source_deleted": all(
                    item.properties.root.get("source_deleted", False) for item in items
                ),
            }
        )
    chosen = items[-1]
    return chosen.model_copy(
        update={"properties": properties, "revision": max(item.revision for item in items)}
    )


def merge_catalog_objects(scopes: tuple[CatalogSnapshot, ...]) -> tuple[CatalogObject, ...]:
    """Combine matching physical IDs rather than making duplicate table projections."""
    grouped: dict[str, list[tuple[str, CatalogObject]]] = defaultdict(list)
    for scope in scopes:
        for item in scope.objects:
            grouped[item.asset_ref.asset_id].append((scope.scope, item))
    return tuple(
        sorted(
            (_merge(tuple(values)) for values in grouped.values()),
            key=lambda item: (item.asset_ref.asset_type, item.asset_ref.asset_id),
        )
    )
