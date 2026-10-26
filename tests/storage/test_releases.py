# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publication requires exact approval and protects frozen source and release facts."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DatabaseError

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.release_parameters import PublishReleaseParams
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.portable_metadata import portable_metadata
from datakeel.core.release_models import annotation_statistics
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.objects import object_store
from datakeel.storage.release_rows import ReleaseEntryRow, ReleaseRow
from datakeel.storage.release_service import (
    get_release,
    iter_release_entries,
    list_release_files,
    list_releases,
)


def published_fixture(db: Database, tmp_path: Path) -> tuple[str, str, str]:
    """Publish a generated local sample through real approval and action execution."""
    path = tmp_path / "publish.txt"
    path.write_text("Generated release sample.", encoding="utf-8")
    dataset = import_paths(db, "release-example", [path], {"purpose": "example"})
    with db.session() as session:
        version = session.scalar(select(VersionRow.id).where(VersionRow.dataset_id == dataset.id))
        assert version is not None
    plan = prepare_action(
        db,
        "publish_release",
        JsonDocument(
            {"dataset_id": dataset.id, "version_id": version, "tag": "v1.2.0", "notes": "Example"}
        ),
    )
    assert plan.requires_approval
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.receipt is not None
    return dataset.id, version, run.receipt.outputs[0].asset_id


def test_publication_without_approval_is_denied(db: Database, tmp_path: Path) -> None:
    """An irreversible release cannot bypass the existing user approval rules."""
    dataset, version, _release = published_fixture(db, tmp_path)
    plan = prepare_action(
        db,
        "publish_release",
        JsonDocument({"dataset_id": dataset, "version_id": version, "tag": "v1.2.1"}),
    )
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert len(list_releases(db, dataset)) == 1


def test_release_keeps_source_metadata_frozen_and_pages_files(db: Database, tmp_path: Path) -> None:
    """Later dataset edits cannot alter release metadata, file facts, or source provenance."""
    dataset, version, identifier = published_fixture(db, tmp_path)
    with db.session() as session:
        session.execute(
            update(DatasetRow)
            .where(DatasetRow.id == dataset)
            .values(metadata_values={"purpose": "changed"})
        )
        session.commit()
    frozen = get_release(db, identifier)
    assert frozen.metadata == {"purpose": "example"}
    assert frozen.file_count == 1
    assert frozen.tag == "v1.2.0"
    page = list_release_files(db, identifier, 0, 1)
    assert page.next_offset is None
    assert page.files[0].source_version == version
    assert page.files[0].lineage_refs == (version,)
    assert "object_key" not in page.model_dump_json()
    with db.session() as session:
        stored = list(iter_release_entries(session, identifier))
    assert len(stored) == 1
    assert stored[0].object_key


@pytest.mark.parametrize("target", ["release", "entry", "version", "delete", "append"])
def test_published_manifest_and_metadata_reject_direct_edits(
    db: Database, tmp_path: Path, target: str
) -> None:
    """Database constraints enforce immutability beyond the public read-only API."""
    _dataset, version, identifier = published_fixture(db, tmp_path)
    statements = {
        "append": insert(ReleaseEntryRow).values(
            release_id=identifier, file_id="appended", ordinal=2, object_key="private", record={}
        ),
        "release": update(ReleaseRow).where(ReleaseRow.id == identifier).values(notes="edited"),
        "entry": update(ReleaseEntryRow)
        .where(ReleaseEntryRow.release_id == identifier)
        .values(record={}),
        "version": update(VersionRow).where(VersionRow.id == version).values(manifest=[]),
        "delete": delete(ReleaseRow).where(ReleaseRow.id == identifier),
    }
    with db.session() as session, pytest.raises(DatabaseError, match="immutable"):
        session.execute(statements[target])
    assert get_release(db, identifier).file_count == 1


def test_duplicate_tag_and_missing_release_rejected(db: Database, tmp_path: Path) -> None:
    """Publication labels identify one immutable release and unknown IDs never resolve."""
    dataset, version, identifier = published_fixture(db, tmp_path)
    with pytest.raises(ConflictError, match="already exists"):
        prepare_action(
            db,
            "publish_release",
            JsonDocument({"dataset_id": dataset, "version_id": version, "tag": "v1.2.0"}),
        )
    with pytest.raises(NotFoundError):
        get_release(db, "missing")
    with pytest.raises(ValidationError):
        list_release_files(db, identifier, -1)


def test_portable_metadata_removes_nested_locations_and_credentials() -> None:
    """Private fields never cross a portable release boundary, including nested collections."""
    result = portable_metadata(
        {
            "purpose": "example",
            "object_key": "private",
            "source_path": "/private/example",
            "nested": {"token": "example", "label": "normal"},
            "items": ["/private/example", {"password": "example", "value": 1}],
            "windows": "C:\\private\\example",
        }
    )
    assert result == {"purpose": "example", "nested": {"label": "normal"}, "items": [{"value": 1}]}
    assert annotation_statistics({"annotation_count": 4, "labels": ["a", "b"]}) == (4, 2)
    assert annotation_statistics({"annotation": {"label": "a"}, "label": "a"}) == (1, 1)


def test_publish_rejects_stale_governance_facts(db: Database, tmp_path: Path) -> None:
    """A user signature cannot publish a later metadata state under an earlier plan digest."""
    dataset, version, _identifier = published_fixture(db, tmp_path)
    plan = prepare_action(
        db,
        "publish_release",
        JsonDocument({"dataset_id": dataset, "version_id": version, "tag": "v2.0.0"}),
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    with db.session() as session:
        session.execute(
            update(DatasetRow)
            .where(DatasetRow.id == dataset)
            .values(metadata_values={"purpose": "changed"})
        )
        session.commit()
    with pytest.raises(ConflictError, match="state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert len(list_releases(db, dataset)) == 1


def test_published_content_rejects_object_overwrite(db: Database, tmp_path: Path) -> None:
    """Immutable object publication rejects alternate bytes under a release's frozen key."""
    _dataset, _version, identifier = published_fixture(db, tmp_path)
    with db.session() as session:
        entry = next(iter_release_entries(session, identifier))
    changed = tmp_path / "changed.txt"
    changed.write_bytes(b"different content")
    with pytest.raises(ConflictError, match="Immutable object"):
        object_store().put(changed, entry.object_key)


@pytest.mark.parametrize("tag", ["v01.0.0", "v1.0.0-01", "v1.0.0-a..b", "1.0", "1.0.0+"])
def test_release_tags_follow_semantic_version_identifiers(tag: str) -> None:
    """Release labels reject malformed versions and ambiguous numeric prerelease identifiers."""
    with pytest.raises(ValueError, match="validation error"):
        PublishReleaseParams(dataset_id="dataset", version_id="version", tag=tag)


def test_concurrent_publication_of_one_tag_has_one_winner(db: Database, tmp_path: Path) -> None:
    """Independent approved plans cannot publish the same dataset label twice."""
    dataset, version, _identifier = published_fixture(db, tmp_path)
    plans = [
        prepare_action(
            db,
            "publish_release",
            JsonDocument({"dataset_id": dataset, "version_id": version, "tag": "v2.0.0"}),
        )
        for _ in range(2)
    ]
    for plan in plans:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))

    def execute(index: int) -> str:
        plan = plans[index]
        try:
            return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).status
        except ConflictError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(execute, range(2)))
    assert sorted(statuses) == ["CONFLICT", "SUCCEEDED"]
    assert len([release for release in list_releases(db, dataset) if release.tag == "v2.0.0"]) == 1
