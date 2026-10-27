# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical metadata content used for no-change detection and projection hashes."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot

from datakeel.core.models import JsonDocument


def object_content(item: CatalogObject) -> JsonDocument:
    """Exclude display order and provenance while retaining semantic definition fields."""
    value = JsonDocument.model_validate(
        item.model_dump(mode="json", exclude={"revision", "producer_event_id"})
    ).root
    properties = dict(item.properties.root)
    if item.asset_ref.asset_type == "column":
        properties = {key: properties.get(key) for key in ("data_type", "nullable", "comment")}
    elif item.asset_ref.asset_type == "table":
        properties = {key: properties.get(key) for key in ("columns", "primary_key", "comment")}
    properties.update(
        {
            key: item.properties.root[key]
            for key in ("integration", "integrations", "source_deleted")
            if key in item.properties.root
        }
    )
    value["properties"] = properties
    return JsonDocument(value)


def canonical_content(snapshot: CatalogSnapshot) -> JsonDocument:
    """Sort object and edge sets so adapter enumeration never changes the snapshot hash."""
    objects: list[JsonValue] = [
        object_content(item).root
        for item in sorted(
            snapshot.objects, key=lambda item: (item.asset_ref.asset_type, item.asset_ref.asset_id)
        )
    ]
    links: list[JsonValue] = [
        JsonDocument.model_validate(
            link.model_dump(mode="json", exclude={"producer_event_id"})
        ).root
        for link in sorted(
            snapshot.links, key=lambda link: (link.kind, link.source.asset_id, link.target.asset_id)
        )
    ]
    return JsonDocument({"scope": snapshot.scope, "objects": objects, "links": links})


def document_hash(document: JsonDocument) -> str:
    """Hash canonical JSON with stable keys and no nonfinite numeric values."""
    encoded = json.dumps(document.root, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()
