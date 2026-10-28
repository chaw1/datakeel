# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Media worker publication includes owned previews, measured quality and file lineage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.pipeline.media import media_pipeline
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.governance_service import get_report
from datakeel.storage.lineage_service import get_graph
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _scan(tmp_path: Path) -> Path:
    path = tmp_path / "scan.ply"
    path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 4\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property ushort label\nend_header\n"
        "0 0 0 1\n1 0 1 2\n0 1 2 3\nnan 0 0 4\n"
    )
    return path


def test_media_worker_publishes_cleaned_scan_preview_and_original_evidence(
    db: Database, tmp_path: Path
) -> None:
    """All six cloud operators run through durable publication and append-only lineage."""
    dataset = import_paths(db, "Generated scan", [_scan(tmp_path)])
    DatabaseQueue(db).submit(dataset.id, "media", media_pipeline(clean=True))
    run_worker(db, once=True)
    versions = list_versions(db, dataset.id)
    assert len(versions) == 2
    processed = versions[-1]
    assert len(processed.manifest) == 1
    file = processed.manifest[0]
    assert file.metadata["pointcloud_probe"]["invalid_count"] == 0
    assert file.metadata["source_pointcloud_probe"]["nan_count"] == 1
    preview = file.metadata["pointcloud_preview"]
    assert "path" not in preview
    assert preview["object_key"].endswith(".png")
    client = TestClient(create_app(db))
    response = client.get(
        f"/api/datasets/{dataset.id}/files/{file.id}/pointcloud-preview",
        params={"version": processed.id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    schema = client.get("/api/openapi.json").json()
    declared = schema["paths"]["/api/datasets/{identifier}/files/{file_id}/pointcloud-preview"][
        "get"
    ]["responses"]["200"]["content"]
    assert set(declared) == {"image/png"}
    assert declared["image/png"]["schema"] == {"type": "string", "format": "binary"}
    assert "Original scan observations" in get_report(db, dataset.id).body
    events = [event for event in get_graph(db).events if event.operator.startswith("pointcloud.")]
    assert {event.operator for event in events} == {
        f"pointcloud.{name}"
        for name in ("probe", "unit_check", "clean", "downsample", "outliers", "preview")
    }
    assert all(event.quality["operator_version"] == "1.0.0" for event in events)
    assert all(len(event.quality["params_sha256"]) == 64 for event in events)
    assert any(ref.asset_type == "file" for event in events for ref in event.inputs)
    assert any(ref.asset_id == preview["artifact_id"] for event in events for ref in event.outputs)


def test_media_worker_finishes_a_batch_with_one_broken_scan_as_partial(
    db: Database, tmp_path: Path
) -> None:
    """A truncated scan is recorded with its reason while the good scan is cleaned."""
    broken = tmp_path / "broken.ply"
    broken.write_bytes(
        b"ply\nformat ascii 1.0\nelement vertex 9\nproperty float x\nend_header\n1 2\n"
    )
    dataset = import_paths(db, "Generated scans", [_scan(tmp_path), broken])
    DatabaseQueue(db).submit(dataset.id, "media", media_pipeline(clean=True))
    run_worker(db, once=True)
    versions = list_versions(db, dataset.id)
    assert len(versions) == 2
    files = {file.filename: file for file in versions[-1].manifest}
    assert files["scan.ply"].metadata["pointcloud_probe"]["invalid_count"] == 0
    assert "pointcloud_error" not in files["scan.ply"].metadata
    failure = files["broken.ply"].metadata["pointcloud_error"]
    assert failure["operator"] == "pointcloud.probe"
    assert "Malformed or truncated" in failure["reason"]
    assert (
        "broken.ply: pointcloud.probe could not process the file" in get_report(db, dataset.id).body
    )
    events = [event for event in get_graph(db).events if event.operator.startswith("pointcloud.")]
    assert len(events) == 6
    assert all(event.quality["partial"] is True for event in events)
    assert all(event.quality["failed_count"] == 1 for event in events)


def test_preview_cannot_escape_dataset_or_version_scope(db: Database, tmp_path: Path) -> None:
    """Preview resolution never trusts a caller-supplied path or another dataset's version."""
    dataset = import_paths(db, "Generated scan", [_scan(tmp_path)])
    other = import_paths(db, "Other scan", [_scan(tmp_path)])
    DatabaseQueue(db).submit(dataset.id, "preview", media_pipeline())
    run_worker(db, once=True)
    original, processed = list_versions(db, dataset.id)
    file = processed.manifest[0]
    client = TestClient(create_app(db))
    base = f"/api/datasets/{dataset.id}/files/{file.id}/pointcloud-preview"
    assert client.get(base, params={"version": original.id}).status_code == 404
    assert (
        client.get(base, params={"version": list_versions(db, other.id)[0].id}).status_code == 404
    )
    assert (
        client.get(
            f"/api/datasets/{other.id}/files/{file.id}/pointcloud-preview",
            params={"version": processed.id},
        ).status_code
        == 404
    )
