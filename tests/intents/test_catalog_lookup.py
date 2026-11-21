# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Live planner discovery must not inherit the prompt snapshot's object ceiling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.identity_models import Role, Skill, Team, User
from datakeel.core.models import JsonDocument, utcnow
from datakeel.core.production_catalog_models import LabelSet, ProductionModel
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.core.standard_models import CodeList, FieldStandard, StandardsContract
from datakeel.dataset_store.rows import DatasetRow, VersionRow
from datakeel.intents.catalog import CATALOG_LIMIT, build_catalog, catalog_needs_explore
from datakeel.intents.catalog_lookup import search_catalog_objects
from datakeel.storage.identity_rows import RoleRow, SkillRow, TeamRow, UserRow
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow, ProductionModelRow
from datakeel.storage.production_objects import production_objects
from datakeel.storage.production_queries import list_packages
from datakeel.storage.production_rows import ProductionPackageRow, ProductionProjectRow
from datakeel.storage.release_rows import ReleaseRow
from tests.production_helpers import production_fixture
from tests.standards_support import approved_change

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def users(db: Database, count: int = CATALOG_LIMIT + 2) -> None:
    """Seed enough distinct people to put the last identities outside the prompt."""
    with db.session() as session:
        for index in range(count):
            person = User(id=f"person-{index:03}", display_name=f"Person {index:03}")
            session.add(UserRow(id=person.id, payload=person.model_dump(mode="json")))
        session.commit()


def test_live_names_beyond_snapshot_preserve_exact_priority_and_result_bound(db: Database) -> None:
    """Exact identity beats partial matches; all live names remain discoverable."""
    users(db)
    catalog = build_catalog(db)
    assert len(catalog.of("user")) == CATALOG_LIMIT
    assert catalog.truncated
    assert catalog_needs_explore(catalog, threshold=5000)
    assert not catalog.get("user", "person-061")
    for words in ("person-061", " Person 061 ", "061", "please find Person 061 now"):
        found = search_catalog_objects(db, "user", words)
        assert [entry.id for entry in found] == ["person-061"]
    assert len(search_catalog_objects(db, "user", "person", limit=3)) == 3
    assert len(search_catalog_objects(db, "user", "", limit=2)) == 2
    assert not search_catalog_objects(db, "user", "nobody here")
    assert not search_catalog_objects(db, "user", "", limit=0)
    assert not search_catalog_objects(db, "widget", "")


@pytest.mark.parametrize("kind", ["role", "skill", "team"])
def test_identity_vocabularies_search_past_sixty_and_keep_archived_status(
    db: Database, kind: str
) -> None:
    """The live lookup includes archived identities as data, without offering them as active."""
    with db.session() as session:
        for index in range(CATALOG_LIMIT + 2):
            identifier, name = f"custom-{index:03}", f"Vocabulary {index:03}"
            status = "deleted" if index == CATALOG_LIMIT + 1 else "active"
            if kind == "role":
                value = Role(id=identifier, name=name, status=status)
                row = RoleRow(id=identifier, payload=value.model_dump(mode="json"))
            elif kind == "skill":
                value = Skill(
                    id=identifier, name=name, annotation_type="box", domain="roads", status=status
                )
                row = SkillRow(id=identifier, payload=value.model_dump(mode="json"))
            else:
                value = Team(id=identifier, name=name, status=status)
                row = TeamRow(id=identifier, payload=value.model_dump(mode="json"))
            session.add(row)
        session.commit()
    assert build_catalog(db).truncated
    found = search_catalog_objects(db, kind, "Vocabulary 061")
    assert len(found) == 1
    assert found[0].id == "custom-061"
    assert found[0].status == "deleted"
    assert build_catalog(db).get(kind, found[0].id) is None


def test_models_and_latest_label_sets_are_not_capped_by_production_object_queries(
    db: Database,
) -> None:
    """Search passes both the 60-entry snapshot and the old 100-row projection limit."""
    with db.session() as session:
        for index in range(125):
            identifier = f"catalog-{index:03}"
            model = ProductionModel(
                id=identifier, name=f"Detector {index}", version="1", provider="fake"
            )
            session.add(
                ProductionModelRow(id=identifier, revision=1, payload=model.model_dump(mode="json"))
            )
            for version in (1, 2):
                labels = LabelSet(
                    id=identifier,
                    name=f"Vocabulary {index}",
                    version=version,
                    labels=(),
                    created_at=utcnow(),
                )
                session.add(
                    ProductionLabelSetRow(
                        id=f"{identifier}:{version}",
                        label_set_id=identifier,
                        version=version,
                        payload=labels.model_dump(mode="json"),
                    )
                )
        session.commit()
    catalog = build_catalog(db)
    assert len(production_objects(db, ProductionObjectQuery(kind="model"))) == 100
    assert catalog.truncated
    assert len(catalog.of("model")) == CATALOG_LIMIT
    assert len(catalog.of("label_set")) == CATALOG_LIMIT
    assert search_catalog_objects(db, "model", "Detector 124")[0].id == "catalog-124"
    latest = search_catalog_objects(db, "label_set", "Vocabulary 124")
    assert [(entry.id, entry.size) for entry in latest] == [("catalog-124", 2)]


def test_projects_packages_datasets_and_old_versions_are_live_beyond_snapshot(db: Database) -> None:
    """Every container kind is searched globally, including packages of omitted projects."""
    project, _ = production_fixture(db)
    package = list_packages(db, project.id)[0]
    with db.session() as session:
        for index in range(CATALOG_LIMIT + 2):
            identifier = f"zz-{index:03}"
            session.add(DatasetRow(id=identifier, name=f"Collection {index:03}"))
            cloned = project.model_copy(update={"id": identifier, "name": f"Project {index:03}"})
            session.add(
                ProductionProjectRow(
                    id=identifier,
                    dataset_id=project.dataset_id,
                    payload=cloned.model_dump(mode="json"),
                )
            )
            session.flush()
            partition = package.model_copy(
                update={"id": identifier, "project_id": identifier, "name": f"Package {index:03}"}
            )
            session.add(
                ProductionPackageRow(
                    id=identifier, project_id=identifier, payload=partition.model_dump(mode="json")
                )
            )
            session.add(
                VersionRow(
                    id=identifier, dataset_id=project.dataset_id, created_at=index, manifest=[]
                )
            )
        session.commit()
    catalog = build_catalog(db)
    assert catalog.truncated
    for kind, words, identifier in (
        ("project", "Project 061", "zz-061"),
        ("package", "Package 061", "zz-061"),
        ("dataset", "Collection 061", "zz-061"),
        ("version", "zz-000", "zz-000"),
    ):
        assert catalog.get(kind, identifier) is None
        assert [entry.id for entry in search_catalog_objects(db, kind, words)] == [identifier]
    first = search_catalog_objects(db, "package", "", project_id="zz-061", limit=1)
    assert first[0].parent == "zz-061"


def test_hidden_historical_versions_mark_otherwise_small_snapshot_incomplete(db: Database) -> None:
    """Auto exploration also notices historical versions excluded by the newest-five rule."""
    project, _ = production_fixture(db)
    with db.session() as session:
        session.add_all(
            [
                VersionRow(
                    id=f"history-{index}",
                    dataset_id=project.dataset_id,
                    created_at=index,
                    manifest=[],
                )
                for index in range(6)
            ]
        )
        session.commit()
    catalog = build_catalog(db)
    assert len(catalog.entries) < CATALOG_LIMIT
    assert len(catalog.of("version")) == 5
    assert catalog.truncated
    assert search_catalog_objects(db, "version", "history-0")[0].id == "history-0"


@pytest.mark.parametrize("count", [CATALOG_LIMIT - 1, CATALOG_LIMIT])
def test_release_tagged_versions_reaching_ceiling_trigger_explore(db: Database, count: int) -> None:
    """Saturation triggers exploration even when every historical version has a release tag."""
    with db.session() as session:
        session.add(DatasetRow(id="published", name="Published versions"))
        session.flush()
        for index in range(count):
            identifier = f"published-{index}"
            session.add(
                VersionRow(id=identifier, dataset_id="published", created_at=index, manifest=[])
            )
            session.flush()
            session.add(
                ReleaseRow(
                    id=identifier,
                    dataset_id="published",
                    version_id=identifier,
                    tag=f"v{index}",
                    notes="",
                    created_at=index,
                    manifest_sha256="0" * 64,
                    file_count=0,
                    total_bytes=0,
                    metadata_values={},
                    summary={},
                )
            )
        session.commit()
    catalog = build_catalog(db)
    assert len(catalog.of("version")) == count
    assert catalog.truncated is (count == CATALOG_LIMIT)
    assert catalog_needs_explore(catalog, threshold=5000) is (count == CATALOG_LIMIT)


def test_standards_and_code_lists_search_past_combined_snapshot_limit(db: Database) -> None:
    """The active contract is searched in full even when one category fills the prompt."""
    contract = StandardsContract(
        standards=tuple(
            FieldStandard(
                code=f"field-{index}",
                name_zh=f"字段 {index}",
                name_en=f"Field {index}",
                description="Generated field",
                data_type="string",
            )
            for index in range(CATALOG_LIMIT * 2 + 1)
        ),
        code_lists=(CodeList(code="codes", name="Last vocabulary"),),
    )
    approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )
    catalog = build_catalog(db)
    assert catalog.truncated
    assert len(catalog.of("standard")) == CATALOG_LIMIT * 2
    assert not catalog.of("code_list")
    assert search_catalog_objects(db, "standard", "Field 120")[0].id == "field-120"
    assert search_catalog_objects(db, "code_list", "Last vocabulary")[0].id == "codes"
