# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen selection materialization scans each source once and retains exact source semantics."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import AssetRef, FileItem, utcnow
from datakeel.ontology.models import FrozenManifest, FrozenObject, ObjectSet
from datakeel.storage.action_selection import selected_files
from datakeel.storage.database import DatasetRow, VersionRow

if TYPE_CHECKING:
    from collections.abc import Iterator

    from datakeel.storage.database import Database


def _files(count: int) -> list[FileItem]:
    return [
        FileItem(id=f"file-{index}", path="generated/file.txt", filename=f"file-{index}.txt")
        for index in range(count)
    ]


def _plan(files: list[FileItem], version: str | None = None) -> ActionPlan:
    now = utcnow()
    manifest = FrozenManifest(
        query=ObjectSet(dataset_id="dataset", limit=10000),
        objects=[
            FrozenObject(
                asset_ref=AssetRef(asset_type="file", asset_id=item.id, version=version),
                revision="fixed",
                properties={"dataset_id": "dataset", "version_id": version},
            )
            for item in files
        ],
        state_digest="fixed",
        total_bytes=0,
    )
    return ActionPlan(
        id="plan",
        action_type="create_version_from_selection",
        canonical_params={},
        manifest=manifest,
        plan_digest="fixed",
        target_digest="fixed",
        state_digest="fixed",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        reversible=True,
        external=False,
        impact=ActionImpact(object_count=len(files), total_bytes=0, external=False),
        actor="local",
        context=ActionContext(),
    )


class _CountedManifest(list[dict[str, object]]):
    visits = 0

    def __iter__(self) -> Iterator[dict[str, object]]:
        for entry in super().__iter__():
            self.visits += 1
            yield entry


def test_materialization_when_selection_quadruples_scans_source_linearly(db: Database) -> None:
    """Four times as many selected records require four times as many source visits."""
    visits: list[int] = []
    for count in (100, 400):
        files = _files(count)
        with db.session() as session:
            row = DatasetRow(id="dataset", name="Generated", files=[])
            session.add(row)
            session.flush()
            counted = _CountedManifest(item.model_dump(mode="json") for item in files)
            row.files = counted
            assert selected_files(session, _plan(files)) == files
            visits.append(counted.visits)
            session.rollback()
    assert visits[1] <= visits[0] * 4


def test_materialization_when_sources_interleave_loads_each_source_once(db: Database) -> None:
    """Alternating frozen versions must not cause a database query per selected file."""
    files = _files(16)
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated", files=[]))
        session.flush()
        for version in ("v1", "v2"):
            session.add(
                VersionRow(
                    id=version,
                    dataset_id="dataset",
                    manifest=[item.model_dump(mode="json") for item in files],
                )
            )
        session.commit()
    plan = _plan(files)
    plan = plan.model_copy(
        update={
            "manifest": plan.manifest.model_copy(
                update={
                    "objects": [
                        item.model_copy(
                            update={
                                "properties": {
                                    "dataset_id": "dataset",
                                    "version_id": f"v{index % 2 + 1}",
                                }
                            }
                        )
                        for index, item in enumerate(plan.manifest.objects)
                    ]
                }
            )
        }
    )
    statements: list[str] = []

    def observed(*args: object) -> None:
        statements.append(str(args[2]))

    with db.session() as session:
        event.listen(db.engine, "before_cursor_execute", observed)
        try:
            assert selected_files(session, plan) == files
        finally:
            event.remove(db.engine, "before_cursor_execute", observed)
    assert len(statements) <= 4


def test_materialization_when_version_missing_falls_back_and_keeps_first_duplicate(
    db: Database,
) -> None:
    """Keep the existing missing-version fallback and first-entry-wins manifest behavior."""
    first = _files(1)[0]
    duplicate = first.model_copy(update={"filename": "later.txt"})
    with db.session() as session:
        session.add(
            DatasetRow(
                id="dataset",
                name="Generated",
                files=[first.model_dump(mode="json"), duplicate.model_dump(mode="json")],
            )
        )
        session.commit()
    with db.session() as session:
        assert selected_files(session, _plan([first], "missing-version")) == [first]


def test_materialization_when_dataset_or_selected_file_missing_preserves_errors(
    db: Database,
) -> None:
    """Missing source ownership and missing frozen identities retain distinct domain errors."""
    plan = _plan(_files(1))
    with db.session() as session, pytest.raises(NotFoundError, match="dataset no longer"):
        selected_files(session, plan)
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated", files=[]))
        session.commit()
    with db.session() as session, pytest.raises(ConflictError, match="frozen version"):
        selected_files(session, plan)
