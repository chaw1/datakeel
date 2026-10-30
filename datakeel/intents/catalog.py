# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Name-to-identity lookup for the objects a person can mention in one sentence."""

from pydantic import Field

from datakeel.core.intent_models import Candidate
from datakeel.core.models import BoundaryModel
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets, list_versions
from datakeel.storage.identity_store import list_users
from datakeel.storage.production_objects import production_objects
from datakeel.storage.production_queries import list_packages, list_projects
from datakeel.storage.standard_store import get_contract

CATALOG_LIMIT = 60
MIN_NAME = 2

# Parameter names whose values identify one existing object of the given kind.
FIELD_KINDS: dict[str, str] = {
    "dataset_id": "dataset",
    "version_id": "version",
    "project_id": "project",
    "package_id": "package",
    "label_set_id": "label_set",
    "actor": "user",
    "user_id": "user",
    "holder": "user",
    "task_id": "task",
}


class CatalogEntry(BoundaryModel):
    """One object a sentence may name, with every spelling that identifies it."""

    kind: str
    id: str
    label: str
    names: tuple[str, ...] = ()
    parent: str | None = None
    size: int | None = None


class EntityCatalog(BoundaryModel):
    """Bounded snapshot of users, projects, datasets, versions, label sets and standards."""

    entries: list[CatalogEntry] = Field(default_factory=list[CatalogEntry])

    def of(self, kind: str, parent: str | None = None) -> list[CatalogEntry]:
        """List entries of one kind, optionally inside one parent object."""
        return [
            entry
            for entry in self.entries
            if entry.kind == kind and (parent is None or entry.parent == parent)
        ]

    def get(self, kind: str, identifier: str) -> CatalogEntry | None:
        """Return the entry with this exact identity."""
        return next((entry for entry in self.of(kind) if entry.id == identifier), None)

    def match(self, kind: str, text: str, parent: str | None = None) -> list[CatalogEntry]:
        """Resolve an identity or a spoken name; exact spellings win over partial ones."""
        wanted = text.strip().casefold()
        if not wanted:
            return []
        pool = self.of(kind, parent)
        exact = [
            entry
            for entry in pool
            if wanted in {entry.id.casefold(), *(name.casefold() for name in entry.names)}
        ]
        if exact:
            return exact
        return [
            entry
            for entry in pool
            if any(
                wanted in name.casefold() or (len(name) >= MIN_NAME and name.casefold() in wanted)
                for name in entry.names
            )
        ]

    def mentioned(self, kind: str, text: str) -> list[CatalogEntry]:
        """Find entries of one kind whose name appears literally in the sentence."""
        lowered = text.casefold()
        found = [
            entry
            for entry in self.of(kind)
            if any(len(name) >= MIN_NAME and name.casefold() in lowered for name in entry.names)
        ]
        longest = {
            entry.id: max((len(n) for n in entry.names if n.casefold() in lowered), default=0)
            for entry in found
        }
        return sorted(found, key=lambda entry: -longest[entry.id])


def candidates(entries: list[CatalogEntry]) -> list[Candidate]:
    """Present catalog entries as choices."""
    return [Candidate(id=entry.id, label=entry.label, kind=entry.kind) for entry in entries][:10]


def build_catalog(db: Database, project_id: str | None = None) -> EntityCatalog:
    """Read the objects a request can name; every list is bounded."""
    entries = [
        CatalogEntry(
            kind="user",
            id=user.id,
            label=user.display_name,
            names=(user.id, user.display_name),
        )
        for user in list_users(db)[:CATALOG_LIMIT]
        if user.status == "active"
    ]
    projects = list_projects(db)[:CATALOG_LIMIT]
    entries += [
        CatalogEntry(
            kind="project",
            id=project.id,
            label=project.name,
            names=(project.id, project.name),
            parent=project.dataset_id,
        )
        for project in projects
    ]
    if project_id and any(project.id == project_id for project in projects):
        entries += [
            CatalogEntry(
                kind="package",
                id=package.id,
                label=package.name,
                names=(package.id, package.name),
                parent=project_id,
                size=package.task_count,
            )
            for package in list_packages(db, project_id)[:CATALOG_LIMIT]
        ]
    for dataset in list_datasets(db)[:CATALOG_LIMIT]:
        entries.append(
            CatalogEntry(
                kind="dataset",
                id=dataset.id,
                label=dataset.name,
                names=(dataset.id, dataset.name),
                size=dataset.file_count,
            )
        )
        entries += [
            CatalogEntry(
                kind="version",
                id=version.id,
                label=f"{dataset.name} · {version.id[:8]}",
                names=(version.id,),
                parent=dataset.id,
                size=version.file_count,
            )
            for version in list_versions(db, dataset.id)[-5:]
        ]
    entries += _label_sets(db) + _standards(db)
    return EntityCatalog(entries=entries)


def _label_sets(db: Database) -> list[CatalogEntry]:
    latest: dict[str, CatalogEntry] = {}
    for item in production_objects(db, ProductionObjectQuery(kind="label_set")):
        properties = item.properties
        name = str(properties.get("name", item.asset_ref.asset_id))
        version = properties.get("version")
        entry = CatalogEntry(
            kind="label_set",
            id=item.asset_ref.asset_id,
            label=f"{name} v{version}",
            names=(item.asset_ref.asset_id, name),
            size=version if isinstance(version, int) else None,
        )
        previous = latest.get(entry.id)
        if previous is None or (entry.size or 0) > (previous.size or 0):
            latest[entry.id] = entry
    return list(latest.values())[:CATALOG_LIMIT]


def _standards(db: Database) -> list[CatalogEntry]:
    contract = get_contract(db)
    fields = [
        CatalogEntry(
            kind="standard",
            id=item.code,
            label=f"{item.name_zh} / {item.name_en}",
            names=(item.code, item.name_zh, item.name_en, *item.aliases),
        )
        for item in contract.standards
    ]
    lists = [
        CatalogEntry(
            kind="code_list",
            id=item.code,
            label=item.name,
            names=(item.code, item.name),
            size=len(item.entries),
        )
        for item in contract.code_lists
    ]
    return (fields + lists)[: CATALOG_LIMIT * 2]
