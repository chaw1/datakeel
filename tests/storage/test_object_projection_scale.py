# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Object projection keeps legacy version choices while bounding manifest and state reads."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from datakeel.core.models import FileItem
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.evidence_snapshot import EvidenceSnapshot
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.object_projection import project_objects

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Connection

    from datakeel.ontology.models import FrozenObject
    from datakeel.storage.database import Database

_VERSIONS = (
    ("old-a", 100, None),
    ("old-z", 100, None),
    ("mid", 200, "task-mid"),
    ("new-a", 300, "task-a"),
    ("new-z", 300, "task-z"),
    ("source-newest", 400, None),
)


def _seed(database: Database, count: int = 3) -> None:
    with database.session() as session:
        dataset = DatasetRow(id="projection", name="Generated", files=[])
        session.add(dataset)
        session.flush()
        for identifier, created, task in _VERSIONS:
            manifest = [
                FileItem(
                    id=f"file-{index}",
                    filename=f"{identifier}-{index}.txt",
                    path="",
                    modality="text",
                    size=1,
                    sha256=f"{index:064x}",
                ).model_dump(mode="json")
                for index in range(count)
            ]
            session.add(
                VersionRow(
                    id=identifier,
                    dataset_id=dataset.id,
                    created_at=created,
                    task_id=task,
                    manifest=manifest,
                )
            )
        session.commit()


def _project(database: Database, query: ObjectSet) -> list[FrozenObject]:
    with database.session() as session:
        dataset = session.get(DatasetRow, "projection")
        assert dataset is not None
        return project_objects(session, [dataset], query, EvidenceSnapshot(subjects={}))


@contextmanager
def _reads(database: Database) -> Iterator[tuple[list[str], list[str]]]:
    statements: list[str] = []
    versions: list[str] = []

    def record(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        if statement.startswith("SELECT"):
            statements.append(statement)

    def loaded(row: VersionRow, _context: object) -> None:
        versions.append(row.id)

    event.listen(database.engine, "before_cursor_execute", record)
    event.listen(VersionRow, "load", loaded)
    try:
        yield statements, versions
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
        event.remove(VersionRow, "load", loaded)


@pytest.mark.parametrize("kind", ["file", "artifact"])
def test_default_projection_reads_one_manifest_and_one_state_batch(db: Database, kind: str) -> None:
    """A file count increase does not multiply state queries or load unrelated versions."""
    _seed(db, count=33)
    with _reads(db) as (statements, versions):
        values = _project(db, ObjectSet(object_type=kind))
    assert len(values) == 33
    assert len(versions) == 1
    assert sum("FROM file_states" in statement for statement in statements) == 1
    version_queries = [statement for statement in statements if "FROM versions" in statement]
    limited = [statement for statement in version_queries if "LIMIT" in statement]
    assert len(limited) == 1
    # The file projection also indexes same-byte media measurements, but that read is
    # filtered to manifests carrying a measurement and decoded nothing here.
    assert len(version_queries) == (2 if kind == "file" else 1)
    assert all("LIKE" in statement for statement in version_queries if statement not in limited)


@pytest.mark.parametrize(("kind", "expected"), [("file", "old-z"), ("artifact", "new-a")])
def test_default_projection_preserves_legacy_time_and_identity_ties(
    db: Database, kind: str, expected: str
) -> None:
    """Files choose oldest/max-ID ties; artifacts choose newest/min-ID task versions."""
    _seed(db)
    values = _project(db, ObjectSet(object_type=kind))
    assert {value.asset_ref.version for value in values} == {expected}


def test_explicit_versions_and_time_ranges_keep_every_matching_manifest(db: Database) -> None:
    """LIMIT applies only to implicit defaults, with existing ordering retained elsewhere."""
    _seed(db)
    explicit = _project(db, ObjectSet(version_ids=["new-z", "old-a"]))
    ranged = _project(
        db,
        ObjectSet(
            created_after=datetime.fromtimestamp(150, UTC),
            created_before=datetime.fromtimestamp(300, UTC),
        ),
    )
    all_versions = _project(db, ObjectSet(object_type="version"))
    assert [value.asset_ref.version for value in explicit[::3]] == ["new-z", "old-a"]
    assert [value.asset_ref.version for value in ranged[::3]] == ["new-a", "new-z", "mid"]
    assert [value.asset_ref.version for value in all_versions] == [
        "source-newest",
        "new-a",
        "new-z",
        "mid",
        "old-a",
        "old-z",
    ]


def test_batched_state_preserves_deletion_quarantine_revision_and_dataset_scope(
    db: Database,
) -> None:
    """Current mutable state overlays all immutable versions without crossing datasets."""
    _seed(db)
    with db.session() as session:
        session.add(DatasetRow(id="other", name="Other generated dataset", files=[]))
        session.flush()
        session.add_all(
            [
                FileStateRow(
                    dataset_id="projection", file_id="file-0", quarantined=True, revision=4
                ),
                FileStateRow(dataset_id="projection", file_id="file-1", deleted=True, revision=7),
                FileStateRow(dataset_id="other", file_id="file-2", deleted=True, revision=9),
            ]
        )
        session.commit()
    visible = _project(db, ObjectSet())
    all_files = _project(db, ObjectSet(include_deleted=True))
    assert [value.asset_ref.asset_id for value in visible] == ["file-0", "file-2"]
    assert visible[0].properties["quarantined"] is True
    assert visible[0].state_revision == 4
    assert visible[1].state_revision == 0
    deleted = next(value for value in all_files if value.asset_ref.asset_id == "file-1")
    assert deleted.properties["deleted"] is True
    assert deleted.state_revision == 7
