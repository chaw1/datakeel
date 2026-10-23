# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical identity and explicit containment construction for import adapters."""

from pydantic import BaseModel

from datakeel.core.catalog_identity import catalog_segments
from datakeel.core.catalog_models import CatalogKind, CatalogLink, CatalogObject
from datakeel.core.models import AssetRef, JsonDocument


def metadata_object(
    kind: CatalogKind, asset_id: str, name: str, properties: BaseModel
) -> CatalogObject:
    """Construct one metadata object from an explicitly typed property document."""
    parts = catalog_segments(asset_id)
    return CatalogObject(
        asset_ref=AssetRef(asset_type=kind, asset_id=asset_id, display_name=name),
        name=name,
        source_id=parts[0],
        schema_name=parts[1] if len(parts) > 1 else None,
        table_id="/".join(asset_id.split("/")[:3]) if kind == "column" else None,
        properties=JsonDocument.model_validate(properties.model_dump(mode="json")),
    )


def contains(parent: CatalogObject, child: CatalogObject) -> CatalogLink:
    """Record containment separately from computed column derivation."""
    return CatalogLink(source=parent.asset_ref, target=child.asset_ref, kind="contains")
