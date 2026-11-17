# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image-folder upload shares chunk verification and freezes source pairing."""

import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from datakeel.api.app import create_app
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.uploads import UploadInput
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.training_inputs import load_training_samples


def _png() -> bytes:
    result = BytesIO()
    Image.new("RGB", (12, 12), color="red").save(result, format="PNG")
    return result.getvalue()


def _request(entries: tuple[tuple[str, bytes], ...]) -> UploadInput:
    payload = b"".join(content for _, content in entries)
    return UploadInput.model_validate(
        {
            "idempotency_key": "review-folder",
            "name": "Generated paired images",
            "filename": "folder.bin",
            "total_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "chunk_bytes": len(payload) - 1,
            "folder": [{"path": path, "size": len(content)} for path, content in entries],
        }
    )


def test_folder_upload_can_resume_and_publishes_one_version_with_paired_labels(
    db: Database,
) -> None:
    """Resume the exact folder and preserve source paths, labels, and unknown annotations."""
    image = _png()
    entries = (
        ("train/sample-a/image.png", image),
        ("train/sample-a/caption.txt", b"A generated animal."),
        (
            "train/sample-a/annotations.json",
            b'{"annotations":[{"category":"animal","bbox":[0,0,5,5]}]}',
        ),
        ("test/sample-b/image.png", image),
        ("test/sample-b/annotations.json", b"not a valid annotation document"),
    )
    request = _request(entries)
    data = request.model_dump(mode="json")
    content = b"".join(body for _, body in entries)
    client = TestClient(create_app(db, run_migrations=False))
    started = client.post("/api/uploads", json=data)
    assert started.status_code == 201, started.text
    path = f"/api/uploads/{started.json()['id']}"
    assert client.put(f"{path}/chunks/1", content=content[-1:]).status_code == 200
    assert client.post(f"{path}/complete").status_code == 422
    assert client.post("/api/uploads", json=data).json()["missing_chunks"] == [0]
    assert client.put(f"{path}/chunks/0", content=content[:-1]).status_code == 200
    response = client.post(f"{path}/complete")
    assert response.status_code == 200, response.text
    dataset_id = response.json()["dataset_id"]
    assert client.post(f"{path}/complete").json()["dataset_id"] == dataset_id
    assert client.get(f"/api/datasets/{dataset_id}").json()["metadata"]["evidence_samples"]
    versions = client.get(f"/api/datasets/{dataset_id}/versions").json()
    assert len(versions) == 1
    version, manifest = source_manifest(db, dataset_id)
    assert [entry.filename for entry in manifest] == [entries[3][0], entries[0][0]]
    facts = sample_sidecars(manifest[1])
    assert facts.caption is not None
    assert facts.caption.path == entries[1][0]
    assert facts.annotation is not None
    assert facts.annotation.path == entries[2][0]
    samples = {item.file.filename: item for item in load_training_samples(db, dataset_id, version)}
    assert samples[entries[0][0]].labels == ("animal",)
    assert samples[entries[3][0]].annotations[0].labels is None


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ((("train/../escaped.png", b"a"),), "portable relative path"),
        ((("train/scene\\escaped.png", b"a"),), "portable relative path"),
        ((("/train/escaped.png", b"a"),), "portable relative path"),
        ((("train/a.png", b"a"), ("train/a.png", b"b")), "conflicting paths"),
        ((("train/a.png", b"a"), ("train/a.png/child.jpg", b"b")), "conflicting paths"),
        ((("train/caption.txt", b"a"),), "no supported images"),
        ((("train/blob.exe", b"a"),), "text and JSON sidecar"),
    ],
)
def test_folder_manifest_rejects_ambiguous_or_unsupported_members(
    entries: tuple[tuple[str, bytes], ...], message: str
) -> None:
    """Reject paths at declaration before disk staging or content publication."""
    # The declaration helper must use a nonzero chunk size even for a one-byte fixture.
    expanded = tuple((path, content * 2) for path, content in entries)
    with pytest.raises(ValidationError, match=message):
        _request(expanded)


def test_folder_manifest_members_cover_declared_blob() -> None:
    """Reject trailing undisclosed bytes before receiving a chunk."""
    request = _request((("test/a.png", b"short"),))
    with pytest.raises(ValidationError, match="byte count"):
        UploadInput.model_validate({**request.model_dump(), "total_bytes": request.total_bytes + 1})
