# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Binary HTTP resumability with bounded request buffering."""

import hashlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.database import Database
from datakeel.storage.upload_service import start_upload
from tests.storage.test_uploads import declaration


def test_http_chunk_upload_resume_and_download(db: Database) -> None:
    """Resume requests report only absent chunks and completed downloads match originals."""
    client = TestClient(create_app(db))
    payload = b"generated-file"
    request = {
        "idempotency_key": "http-sample",
        "name": "HTTP generated data",
        "filename": "sample.txt",
        "total_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "chunk_bytes": 8,
    }
    response = client.post("/api/uploads", json=request)
    assert response.status_code == 201
    identifier = response.json()["id"]
    prefix = f"/api/uploads/{identifier}"
    rejected = client.put(f"{prefix}/chunks/1", content=payload[8:] + b"x")
    assert rejected.status_code == 422
    assert client.get(prefix).json()["received_chunks"] == []
    assert client.put(f"{prefix}/chunks/1", content=payload[8:]).status_code == 200
    assert client.get(prefix).json()["missing_chunks"] == [0]
    assert client.post("/api/uploads", json=request).json()["id"] == identifier
    assert client.put(f"{prefix}/chunks/0", content=payload[:8]).status_code == 200
    receipt = client.post(f"{prefix}/complete")
    assert receipt.status_code == 200
    dataset = receipt.json()["dataset_id"]
    files = client.get(f"/api/datasets/{dataset}/files").json()
    downloaded = client.get(f"/api/datasets/{dataset}/files/{files[0]['id']}/download")
    assert downloaded.content == payload


def test_http_oversize_chunk_is_bounded(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    """Body bytes over the configured bound never enter staging or publication."""
    monkeypatch.setenv("DATAKEEL_UPLOAD_MAX_CHUNK_BYTES", "4")
    client = TestClient(create_app(db))
    response = client.post(
        "/api/uploads",
        json={
            "idempotency_key": "too-big",
            "name": "Generated data",
            "filename": "sample.bin",
            "total_bytes": 4,
            "sha256": hashlib.sha256(b"abcd").hexdigest(),
            "chunk_bytes": 4,
        },
    )
    prefix = f"/api/uploads/{response.json()['id']}"

    def body() -> Iterator[bytes]:
        yield b"abcd"
        yield b"overflow"

    result = client.put(f"{prefix}/chunks/0", content=body())
    assert result.status_code == 422
    assert "upload_max_chunk_bytes" in result.json()["detail"]
    assert client.get(prefix).json()["received_chunks"] == []


def test_http_concurrent_chunk_conflict_names_upload(db: Database) -> None:
    """A busy chunk request returns a retryable upload-specific HTTP conflict."""
    upload = start_upload(db, declaration(b"abcd"))
    client = TestClient(create_app(db))
    with response_lock(db, f"upload:{upload.id}"):
        response = client.put(f"/api/uploads/{upload.id}/chunks/0", content=b"abcd")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail == "Upload is busy; retry after the active upload operation completes"
    assert "Conversation" not in detail
    assert client.put(f"/api/uploads/{upload.id}/chunks/0", content=b"abcd").status_code == 200
