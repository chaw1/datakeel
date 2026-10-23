# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""File materialization requires an exact source version for every selected asset identity."""

from pathlib import Path
from typing import NamedTuple

import pytest
from sqlalchemy import select

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ConflictError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.ontology.models import ObjectSet, PropertyFilter
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.action_selection import selected_files
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.datasets import materialize_files, persist_file
from datakeel.storage.object_queries import evaluate
from tests.actions.conftest import DatasetFixture


class SourceVersions(NamedTuple):
    """Hold two immutable records with different bytes under one asset identity."""

    selection: ObjectSet
    original_bytes: bytes
    replacement_bytes: bytes


def _versions(db: Database, dataset: DatasetFixture, directory: Path) -> SourceVersions:
    created, files = dataset
    replacement_path = directory / "replacement.txt"
    replacement_path.write_text(
        "Independent replacement content for the same asset", encoding="utf-8"
    )
    with db.session() as session:
        source = session.scalar(select(VersionRow).where(VersionRow.dataset_id == created.id))
        assert source is not None
        original_file = FileItem.model_validate(
            next(raw for raw in source.manifest if raw["id"] == files[1].id)
        )
        replacement = persist_file(original_file.model_copy(update={"path": str(replacement_path)}))
        newer = VersionRow(
            dataset_id=created.id,
            manifest=[replacement.model_dump(mode="json")],
            created_at=source.created_at + 10,
        )
        session.add(newer)
        session.flush()
        selection = ObjectSet(
            dataset_id=created.id,
            version_ids=[source.id, newer.id],
            filters=[PropertyFilter(field="id", value=original_file.id)],
        )
        session.commit()
    return SourceVersions(
        selection, Path(original_file.path).read_bytes(), replacement_path.read_bytes()
    )


def test_create_version_when_same_asset_has_multiple_sources_rejects_before_preparation(
    db: Database, dataset: DatasetFixture, tmp_path: Path
) -> None:
    """Never silently choose one of two different source contents for the same asset."""
    versions = _versions(db, dataset, tmp_path)
    assert versions.original_bytes != versions.replacement_bytes
    assert len(evaluate(db, versions.selection).objects) == 2
    with pytest.raises(ConflictError, match="one exact source version"):
        prepare_action(
            db,
            "create_version_from_selection",
            JsonDocument({"selection": versions.selection.model_dump(mode="json")}),
        )
    with db.session() as session:
        assert list(session.scalars(select(ActionPlanRow))) == []


@pytest.mark.parametrize("source_index", [0, 1])
def test_create_version_when_one_source_selected_preserves_its_exact_bytes(
    db: Database, dataset: DatasetFixture, tmp_path: Path, source_index: int
) -> None:
    """Allow either explicit source version and publish its selected immutable content."""
    versions = _versions(db, dataset, tmp_path)
    selection = versions.selection.model_copy(
        update={"version_ids": [versions.selection.version_ids[source_index]]}
    )
    plan = prepare_action(
        db,
        "create_version_from_selection",
        JsonDocument({"selection": selection.model_dump(mode="json")}),
    )
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert result.status == "SUCCEEDED"
    assert result.receipt is not None
    output = next(ref for ref in result.receipt.outputs if ref.asset_type == "version")
    with db.session() as session:
        published = session.get(VersionRow, output.asset_id)
        assert published is not None
        materialized = materialize_files(published.manifest)
    assert len(materialized) == 1
    expected = versions.original_bytes if source_index == 0 else versions.replacement_bytes
    assert Path(materialized[0].path).read_bytes() == expected


def test_materialization_when_ambiguous_frozen_manifest_rejects_at_shared_boundary(
    db: Database, dataset: DatasetFixture, tmp_path: Path
) -> None:
    """Protect all selected_files callers while retaining shared-ID state-overlay selection."""
    versions = _versions(db, dataset, tmp_path)
    plan = prepare_action(
        db,
        "quarantine_files",
        JsonDocument({"selection": versions.selection.model_dump(mode="json")}),
    )
    with db.session() as session, pytest.raises(ConflictError, match="one exact source version"):
        selected_files(session, plan)
