# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real approved releases export and verify through the offline recipient engine."""

import json
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.delivery.reconcile import reconcile
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.delivery_service import (
    export_release,
    list_reconciliations,
    reconcile_release,
)
from datakeel.storage.objects import LocalStore, object_store
from datakeel.storage.release_service import iter_release_entries


@pytest.fixture
def release(db: Database, tmp_path: Path) -> str:
    """Publish two generated objects using the actual approval and execution boundary."""
    paths = [tmp_path / "one:sample?.txt", tmp_path / ("样" * 80 + ".txt")]
    for index, path in enumerate(paths):
        path.write_text(f"Generated delivery sample {index}.\n", encoding="utf-8")
    dataset = import_paths(
        db, "delivery-example", paths, {"purpose": "example", "token": "private"}
    )
    with db.session() as session:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert version is not None
        version.manifest = [
            {
                **item,
                "metadata": {
                    **item["metadata"],
                    "labels": ["/m/01yrx", "a"],
                    "annotations": ["box"],
                },
            }
            for item in version.manifest
        ]
        identifier = version.id
        session.commit()
    plan = prepare_action(
        db,
        "publish_release",
        JsonDocument({"dataset_id": dataset.id, "version_id": identifier, "tag": "v1.0.0"}),
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.receipt is not None
    return run.receipt.outputs[0].asset_id


@pytest.mark.parametrize("name", ["directory", "delivery.tar", "delivery.tar.gz"])
def test_export_release_passes_offline_and_has_no_storage_locations(
    db: Database, release: str, tmp_path: Path, name: str
) -> None:
    """Each exported form includes independently verifiable facts and no private object keys."""
    destination = export_release(db, release, tmp_path / name)
    assert reconcile(destination).passed
    if destination.is_dir():
        document = (destination / "MANIFEST.json").read_text()
    else:
        with tarfile.open(destination) as archive:
            stream = archive.extractfile("MANIFEST.json")
            assert stream is not None
            document = stream.read().decode()
    assert "one%3Asample%3F.txt" in document
    assert all(len(Path(item["path"]).name) <= 200 for item in json.loads(document)["files"])
    assert "object_key" not in document
    assert "token" not in document
    assert str(tmp_path) not in document
    assert json.loads(document)["metadata"] == {"purpose": "example"}
    for item in json.loads(document)["files"]:
        assert item["metadata"]["labels"] == ["/m/01yrx", "a"]
        assert item["label_count"] == 2
    with pytest.raises(ConflictError, match="already exists"):
        export_release(db, release, destination)


@pytest.mark.parametrize("fault", ["byte", "missing"])
def test_platform_reconciliation_archives_actual_object_corruption(
    db: Database, release: str, fault: str
) -> None:
    """Backend corruption fails the same offline checks and remains queryable in history."""
    pristine = reconcile_release(db, release)
    assert pristine.passed
    with db.session() as session:
        entry = next(iter_release_entries(session, release))
    path = object_store().materialize(entry.object_key)
    if fault == "byte":
        path.write_bytes(b"X" + path.read_bytes()[1:])
    else:
        path.unlink()
    corrupted = reconcile_release(db, release)
    assert not corrupted.passed
    assert any(item.name == "hashes" and not item.passed for item in corrupted.categories)
    assert [item.id for item in list_reconciliations(db, release)] == [pristine.id, corrupted.id]


def test_export_refuses_corrupt_storage_and_unknown_release(
    db: Database, release: str, tmp_path: Path
) -> None:
    """Export never publishes a manifest claiming corrupt backend bytes are pristine."""
    with db.session() as session:
        entry = next(iter_release_entries(session, release))
    object_store().materialize(entry.object_key).write_bytes(b"changed")
    with pytest.raises(ConflictError, match="differs"):
        export_release(db, release, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()
    with pytest.raises(NotFoundError):
        list_reconciliations(db, "missing")


def test_published_local_object_cannot_be_overwritten(
    db: Database, release: str, tmp_path: Path
) -> None:
    """Local object publication rejects different bytes under an already frozen key."""
    with db.session() as session:
        entry = next(iter_release_entries(session, release))
    source = tmp_path / "altered"
    source.write_bytes(b"malicious overwrite")
    with pytest.raises(ConflictError, match="Immutable"):
        LocalStore().put(source, entry.object_key)
    assert reconcile_release(db, release).passed


def test_delivery_api_download_and_archived_six_category_history(
    db: Database, release: str
) -> None:
    """HTTP exposes portable downloads and every check/difference in archived reports."""
    with TestClient(create_app(db)) as client:
        response = client.post(f"/api/releases/{release}/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"
        assert response.content[:2] == b"\x1f\x8b"
        receipt = client.post(f"/api/releases/{release}/reconcile")
        assert receipt.status_code == 200
        assert receipt.json()["passed"] is True
        assert len(receipt.json()["categories"]) == 6
        history = client.get(f"/api/releases/{release}/reconciliations")
        assert history.json() == [receipt.json()]
        assert client.post("/api/releases/missing/export").status_code == 404
