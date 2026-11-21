# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Name-to-identity lookup for the objects a person can mention in one sentence."""

from pydantic import Field

from datakeel.core.errors import DatakeelError
from datakeel.core.intent_models import Candidate
from datakeel.core.models import BoundaryModel
from datakeel.core.production_models import Project
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.dataset_store.dataset_service import list_datasets, list_versions
from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_roles, list_skills, list_teams, list_users
from datakeel.storage.production_objects import production_objects
from datakeel.storage.production_queries import list_packages, list_projects
from datakeel.storage.release_service import list_releases
from datakeel.storage.standard_store import get_contract

CATALOG_LIMIT = 60
CANDIDATE_LIMIT = 5
MIN_NAME = 2
# The speaker in either language; resolved to the person who typed the sentence.
SELF_WORDS = frozenset({"我", "我自己", "本人", "自己", "me", "myself", "i", "my", "mine", "我的"})

# The template roles as people call them ("标注员", "质检员").
ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "administrator": ("管理员",),
    "project_manager": ("项目经理", "项目负责人"),
    "annotator": ("标注员",),
    "reviewer": ("质检员", "审核员"),
    "acceptance": ("验收观察员",),
}
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
    "leader_id": "user",
    "assignee": "user",
    "annotator_id": "user",
    "task_id": "task",
    "role_id": "role",
    "skill_id": "skill",
    "team_id": "team",
    "model_id": "model",
}
# List parameters whose items each identify one object of the given kind.
LIST_KINDS: dict[str, str] = {
    "role_ids": "role",
    "skill_ids": "skill",
    "team_ids": "team",
    "label_set_ids": "label_set",
    "annotation_dataset_ids": "dataset",
    "add_skill_ids": "skill",
    "remove_skill_ids": "skill",
    "add_team_ids": "team",
    "remove_team_ids": "team",
}


class CatalogEntry(BoundaryModel):
    """One object a sentence may name, with every spelling that identifies it."""

    kind: str
    id: str
    label: str
    names: tuple[str, ...] = ()
    parent: str | None = None
    size: int | None = None
    status: str = "active"
    # Facts the planner needs beside the name, e.g. a skill's annotation type and domain.
    note: str = ""


class EntityCatalog(BoundaryModel):
    """Bounded snapshot of users, projects, datasets, versions, label sets and standards."""

    entries: list[CatalogEntry] = Field(default_factory=list[CatalogEntry])
    truncated: bool = False

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
    """Present catalog entries as choices; a disabled account is never offered."""
    return [
        Candidate(id=entry.id, label=entry.label, kind=entry.kind)
        for entry in entries
        if entry.status == "active"
    ][:CANDIDATE_LIMIT]


def catalog_needs_explore(catalog: EntityCatalog, *, threshold: int) -> bool:
    """Use read-first planning when the snapshot is incomplete or too large."""
    return catalog.truncated or len(catalog.entries) >= threshold


def build_catalog(db: Database, project_id: str | None = None) -> EntityCatalog:
    """Read bounded categories, retaining whether any category reached its ceiling."""
    entries: list[CatalogEntry] = []
    truncated = False

    def add(group: list[CatalogEntry], limit: int = CATALOG_LIMIT) -> None:
        nonlocal truncated
        truncated |= len(group) >= limit
        entries.extend(group[:limit])

    add(
        [
            CatalogEntry(
                kind="user",
                id=u.id,
                label=u.display_name,
                names=(u.id, u.display_name),
                status=u.status,
            )
            for u in list_users(db)
        ]
    )
    projects = list_projects(db)
    add(
        [
            CatalogEntry(
                kind="project", id=p.id, label=p.name, names=(p.id, p.name), parent=p.dataset_id
            )
            for p in projects
        ]
    )
    for project in sorted(projects[:CATALOG_LIMIT], key=lambda p: p.id != project_id):
        add(catalog_packages(db, (project,), project_id))
    datasets = list_datasets(db)
    add(
        [
            CatalogEntry(
                kind="dataset", id=d.id, label=d.name, names=(d.id, d.name), size=d.file_count
            )
            for d in datasets
        ]
    )
    for dataset in datasets[:CATALOG_LIMIT]:
        versions = catalog_versions(db, dataset.id, dataset.name)
        truncated |= len(versions) >= CATALOG_LIMIT or len(list_versions(db, dataset.id)) > len(
            versions
        )
        entries.extend(versions)
    add(catalog_label_sets(db))
    add(catalog_standards(db), CATALOG_LIMIT * 2)
    people = catalog_people(db)
    for kind in ("role", "skill", "team"):
        add([entry for entry in people if entry.kind == kind])
    add(catalog_models(db))
    return EntityCatalog(entries=entries, truncated=truncated)


def catalog_versions(
    db: Database, dataset: str, name: str, *, all_versions: bool = False
) -> list[CatalogEntry]:
    """The newest versions, and every version a release tag names ("门店货架 v2.0.0")."""
    tags: dict[str, list[str]] = {}
    try:
        for release in list_releases(db, dataset):
            tags.setdefault(release.version_id, []).append(release.tag)
    except DatakeelError:
        tags = {}
    versions = list(enumerate(list_versions(db, dataset), start=1))
    newest = {version.id for _, version in versions[-5:]}
    return [
        CatalogEntry(
            kind="version",
            id=version.id,
            label=f"{name} · v{number}"
            + (f" ({', '.join(tags[version.id])})" if version.id in tags else ""),
            names=(
                version.id,
                f"{name} · v{number}",  # the label the planner is shown, copied back
                *(
                    said
                    for tag in tags.get(version.id, [])
                    for said in (tag, f"{name} {tag}", f"{name}{tag}", f"{name} · {tag}")
                ),
            ),
            parent=dataset,
            size=version.file_count,
        )
        for number, version in versions
        if all_versions or version.id in newest or version.id in tags
    ]


def catalog_packages(
    db: Database, projects: tuple[Project, ...], project_id: str | None
) -> list[CatalogEntry]:
    """Every project's packages: a sentence may name a package of a project it is not on.

    The page's project comes first so its packages win a tie on the same name.
    """
    entries: list[CatalogEntry] = []
    for project in sorted(projects, key=lambda project: project.id != project_id):
        entries += [
            CatalogEntry(
                kind="package",
                id=package.id,
                label=f"{project.name} · {package.name}",
                names=(package.id, package.name, f"{project.name} {package.name}"),
                parent=project.id,
                size=package.task_count,
            )
            for package in list_packages(db, project.id)
        ]
    return entries


def catalog_people(db: Database, *, include_inactive: bool = False) -> list[CatalogEntry]:
    """Roles, skills and teams a sentence can name ("as annotator", "the lidar skill")."""
    entries = [
        CatalogEntry(
            kind="role",
            id=role.id,
            label=role.name,
            names=(role.id, role.name, *ROLE_WORDS.get(role.id, ())),
            status=role.status,
        )
        for role in list_roles(db)
        if include_inactive or role.status == "active"
    ]
    entries += [
        CatalogEntry(
            kind="skill",
            id=skill.id,
            label=skill.name,
            names=(skill.id, skill.name),
            note=f"annotation_type={skill.annotation_type} domain={skill.domain}",
            status=skill.status,
        )
        for skill in list_skills(db)
        if include_inactive or skill.status == "active"
    ]
    entries += [
        CatalogEntry(
            kind="team", id=team.id, label=team.name, names=(team.id, team.name), status=team.status
        )
        for team in list_teams(db)
        if include_inactive or team.status == "active"
    ]
    return entries


def catalog_models(db: Database) -> list[CatalogEntry]:
    """Read all model definitions without the production query result ceiling."""
    entries: list[CatalogEntry] = []
    for item in production_objects(db, ProductionObjectQuery(kind="model"), bounded=False):
        name = str(item.properties.get("name", item.asset_ref.asset_id))
        version = item.properties.get("version")
        label = f"{name} {version}" if version else name
        entries.append(
            CatalogEntry(
                kind="model",
                id=item.asset_ref.asset_id,
                label=label,
                names=(item.asset_ref.asset_id, name, label),
            )
        )
    return entries


def catalog_label_sets(db: Database) -> list[CatalogEntry]:
    """Read the newest vocabulary version for every identity."""
    latest: dict[str, CatalogEntry] = {}
    for item in production_objects(db, ProductionObjectQuery(kind="label_set"), bounded=False):
        name = str(item.properties.get("name", item.asset_ref.asset_id))
        version = item.properties.get("version")
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
    return list(latest.values())


def catalog_standards(db: Database) -> list[CatalogEntry]:
    """Read every standard and code list in the active contract."""
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
    return fields + lists
