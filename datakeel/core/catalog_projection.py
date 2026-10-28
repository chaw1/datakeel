# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuild current metadata deterministically from append-only snapshot events."""

from collections.abc import Iterable

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.metadata_projection import merge_catalog_objects
from datakeel.core.models import LineageEvent

CATALOG_OPERATORS = {"CATALOG_IMPORT", "METRIC_CHANGE", "TERM_CHANGE"}


def snapshot_events(events: Iterable[LineageEvent]) -> list[tuple[LineageEvent, CatalogSnapshot]]:
    """Read only successful metadata events carrying their typed snapshot payload."""
    return [
        (event, CatalogSnapshot.model_validate(event.params["catalog_snapshot"]))
        for event in sorted(events, key=lambda value: (value.occurred_at, value.event_id))
        if event.operator in CATALOG_OPERATORS
        and event.run_state == "COMPLETED"
        and "catalog_snapshot" in event.params
    ]


def project_catalog(events: Iterable[LineageEvent]) -> CatalogSnapshot:
    """Select the latest complete version of each scope and retain its provenance."""
    scopes: dict[str, CatalogSnapshot] = {}
    for _event, snapshot in snapshot_events(events):
        scopes[snapshot.scope] = snapshot
    links = {
        (link.kind, link.source.asset_id, link.target.asset_id): link
        for scope in scopes.values()
        for link in scope.links
    }
    return CatalogSnapshot(
        scope="current",
        objects=merge_catalog_objects(tuple(scopes.values())),
        links=tuple(links[key] for key in sorted(links)),
    )
