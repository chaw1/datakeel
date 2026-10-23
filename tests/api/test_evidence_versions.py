# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence images, selectors, and function results stay pinned to one source version."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from PIL import Image

from datakeel.api.app import create_app
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQueryResult, EvidenceSample
from datakeel.ontology.functions import invoke_function
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.dataset_service import resolve_download
from datakeel.storage.datasets import persist_file
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute
from tests.asgi_client import TestClient
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


class VersionFixture(NamedTuple):
    """Keep two immutable images under one file identity for version-regression assertions."""

    dataset_id: str
    original: str
    newer: str
    file_id: str
    old_bytes: bytes
    new_bytes: bytes


def _versions(db: Database, directory: Path) -> VersionFixture:
    dataset = seed_query_evidence(db, directory / "samples")
    original, files = source_manifest(db, dataset)
    file = files[0]
    old_bytes = resolve_download(db, dataset, file.id, original).path.read_bytes()
    replacement = directory / "replacement.jpg"
    Image.new("RGB", (48, 32), (220, 70, 30)).save(replacement)
    newer_file = persist_file(
        file.model_copy(update={"path": str(replacement), "filename": "replacement.jpg"})
    )
    with db.session() as session:
        version = VersionRow(dataset_id=dataset, manifest=[newer_file.model_dump(mode="json")])
        session.add(version)
        session.flush()
        newer = version.id
        session.commit()
    queue = DatabaseQueue(db)
    queue.submit(dataset, "new-version-evidence", evidence_pipeline(), version_id=newer)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    return VersionFixture(dataset, original, newer, file.id, old_bytes, replacement.read_bytes())


def test_download_when_history_reuses_file_identity_resolves_exact_manifest_and_mime(
    db: Database, tmp_path: Path
) -> None:
    """Historical bytes remain correct even when another version uses the same file identity."""
    versions = _versions(db, tmp_path)
    path = f"/api/datasets/{versions.dataset_id}/files/{versions.file_id}/download"
    with TestClient(create_app(db)) as client:
        legacy = client.get(path)
        old = client.get(path, params={"version": versions.original})
        new = client.get(path, params={"version": versions.newer})
        assert legacy.content == old.content == versions.old_bytes
        assert old.headers["content-type"] == "image/png"
        assert new.content == versions.new_bytes
        assert new.headers["content-type"] == "image/jpeg"
        assert new.content != old.content
        assert client.get(path, params={"version": "missing"}).status_code == 404
        assert client.get(path, params={"version": ""}).status_code == 422
        assert (
            client.get(
                f"/api/evidence/assets/{versions.file_id}", params={"version_id": ""}
            ).status_code
            == 422
        )


def test_download_when_version_belongs_elsewhere_or_omits_file_never_falls_back(
    db: Database, tmp_path: Path
) -> None:
    """A dataset's current file cannot satisfy a missing or foreign historical record."""
    versions = _versions(db, tmp_path)
    with db.session() as session:
        other = DatasetRow(name="another owner", files=[])
        session.add(other)
        session.flush()
        foreign = VersionRow(dataset_id=other.id, manifest=[])
        empty = VersionRow(dataset_id=versions.dataset_id, manifest=[])
        session.add_all([foreign, empty])
        session.flush()
        rejected_versions = [foreign.id, empty.id]
        session.commit()
    path = f"/api/datasets/{versions.dataset_id}/files/{versions.file_id}/download"
    with TestClient(create_app(db)) as client:
        for version in rejected_versions:
            assert client.get(path, params={"version": version}).status_code == 404
            assert (
                client.get(
                    f"/api/evidence/assets/{versions.file_id}", params={"version_id": version}
                ).status_code
                == 404
            )


def test_evidence_when_version_selected_binds_detail_thumbnail_assertions_and_functions(
    db: Database, tmp_path: Path
) -> None:
    """HTTP and both single-sample Functions describe exactly the queried source version."""
    versions = _versions(db, tmp_path)
    with TestClient(create_app(db)) as client:
        query = client.post(
            "/api/evidence/query",
            json={"dataset_id": versions.dataset_id, "version_ids": [versions.newer]},
        )
        sample = EvidenceQueryResult.model_validate(query.json()).items[0]
        detail = EvidenceSample.model_validate(
            client.get(
                f"/api/evidence/assets/{versions.file_id}",
                params={"version_id": sample.source_version},
            ).json()
        )
        assert detail == sample
        assert detail.source_version == versions.newer
        assert detail.assertions
        assert all(item.subject.version == versions.newer for item in detail.assertions)
        assert detail.thumbnail_url is not None
        assert client.get(detail.thumbnail_url).content == versions.new_bytes
        original = EvidenceSample.model_validate(
            client.get(f"/api/evidence/assets/{versions.file_id}").json()
        )
        assert original.source_version == versions.original
        assert original.assertions
        assert {item.id for item in original.assertions}.isdisjoint(
            item.id for item in detail.assertions
        )
    for name in ("get_evidence", "explain_sample"):
        result = invoke_function(
            db,
            name,
            JsonDocument({"asset_id": versions.file_id, "version_id": versions.newer}),
        )
        assert result.asset_refs[0].version == versions.newer
        assert isinstance(result.data, dict)
        assert result.data["asset_ref"] == detail.asset_ref.model_dump(mode="json")
