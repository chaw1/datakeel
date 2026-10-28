# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep the last reflected warehouse columns when an import omits catalog.json."""

from pydantic import JsonValue

from datakeel.catalog.importers.dbt_models import DbtCatalogNode
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot


def catalog_evidence(entry: DbtCatalogNode) -> JsonValue:
    """Record the reflected entry on its table so a later import can reuse it verbatim."""
    return entry.model_dump(mode="json", exclude_defaults=True)


def _details(item: CatalogObject) -> dict[str, JsonValue] | None:
    integration = item.properties.root.get("integration")
    if (
        item.asset_ref.asset_type != "table"
        or item.properties.root.get("source_deleted") is True
        or not isinstance(integration, dict)
    ):
        return None
    details = integration.get("details")
    return details if isinstance(details, dict) else None


def retained_catalog(previous: CatalogSnapshot | None) -> dict[str, DbtCatalogNode]:
    """Rebuild the previous reflection, keyed by every dbt identity of each live table.

    Without catalog.json the warehouse was not read this time, so nothing proves that a
    column disappeared; only an import that supplies catalog.json may delete columns.
    """
    entries: dict[str, DbtCatalogNode] = {}
    for item in previous.objects if previous else ():
        details = _details(item)
        if details is None or not isinstance(reflected := details.get("catalog"), dict):
            continue
        entry = DbtCatalogNode.model_validate(reflected)
        integration = item.properties.root["integration"]
        aliases = details.get("resource_aliases")
        identities = [
            integration.get("unique_id") if isinstance(integration, dict) else None,
            *(aliases if isinstance(aliases, list) else ()),
        ]
        entries.update((identity, entry) for identity in identities if isinstance(identity, str))
    return entries


def retained_columns(snapshot: CatalogSnapshot) -> int:
    """Count the reflected columns a catalog-less import carried over from the last one."""
    count = 0
    for item in snapshot.objects:
        details = _details(item)
        reflected = details.get("catalog") if details else None
        columns = reflected.get("columns") if isinstance(reflected, dict) else None
        count += len(columns) if isinstance(columns, dict) else 0
    return count


def retention_note(count: int) -> str:
    """Explain in the import summary why absent catalog columns were not deleted."""
    if count:
        return (
            f"catalog.json was not provided; kept {count} columns from the previous import "
            "instead of marking them source-deleted"
        )
    return "catalog.json was not provided and no previous import had reflected columns"
