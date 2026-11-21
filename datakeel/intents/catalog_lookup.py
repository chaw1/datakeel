# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Live name discovery independent of the planner's bounded prompt snapshot."""

from functools import partial

from datakeel.dataset_store.dataset_service import list_datasets
from datakeel.intents.catalog import (
    CatalogEntry,
    EntityCatalog,
    catalog_label_sets,
    catalog_models,
    catalog_packages,
    catalog_people,
    catalog_standards,
    catalog_versions,
)
from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_users
from datakeel.storage.production_queries import list_projects


def _objects(db: Database, kind: str, project_id: str | None) -> list[CatalogEntry]:
    if kind == "user":
        return [
            CatalogEntry(
                kind=kind,
                id=u.id,
                label=u.display_name,
                names=(u.id, u.display_name),
                status=u.status,
            )
            for u in list_users(db)
        ]
    if kind == "project":
        return [
            CatalogEntry(
                kind=kind, id=p.id, label=p.name, names=(p.id, p.name), parent=p.dataset_id
            )
            for p in list_projects(db)
        ]
    if kind == "dataset":
        return [
            CatalogEntry(kind=kind, id=d.id, label=d.name, names=(d.id, d.name), size=d.file_count)
            for d in list_datasets(db)
        ]
    if kind == "version":
        return [
            entry
            for d in list_datasets(db)
            for entry in catalog_versions(db, d.id, d.name, all_versions=True)
        ]
    if kind == "package":
        return catalog_packages(db, list_projects(db), project_id)
    readers = {
        **dict.fromkeys(("role", "skill", "team"), partial(catalog_people, include_inactive=True)),
        "label_set": catalog_label_sets,
        "model": catalog_models,
        "standard": catalog_standards,
        "code_list": catalog_standards,
    }
    return readers[kind](db) if kind in readers else []


def search_catalog_objects(
    db: Database, kind: str, words: str, *, project_id: str | None = None, limit: int = 40
) -> list[CatalogEntry]:
    """Search every object of a kind, preserving exact-name priority and bounded output."""
    if limit <= 0:
        return []
    catalog = EntityCatalog(entries=_objects(db, kind, project_id))
    matches = catalog.match(kind, words) if words.strip() else catalog.of(kind)
    return matches[:limit]
