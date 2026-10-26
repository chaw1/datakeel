# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resumable, process-safe chunk uploads with verified atomic dataset publication."""

import json
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.settings import get_settings
from datakeel.core.uploads import UploadInput, UploadView
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.database import Database
from datakeel.storage.datasets import import_dataset
from datakeel.storage.objects import object_store
from datakeel.storage.upload_files import (
    assemble_file,
    expected_bytes,
    persist_chunk,
    received_chunks,
    verify_stored_object,
)
from datakeel.storage.upload_rows import UploadRow


def _require(session: Session, identifier: str) -> UploadRow:
    row = session.get(UploadRow, identifier)
    if row is None:
        message = "Upload not found"
        raise NotFoundError(message)
    return row


def _view(row: UploadRow) -> UploadView:
    body = UploadInput.model_validate(row.declaration)
    received = list(range(body.chunk_count)) if row.dataset_id else received_chunks(row.id, body)
    present = set(received)
    return UploadView(
        id=row.id,
        filename=body.filename,
        total_bytes=body.total_bytes,
        sha256=body.sha256,
        chunk_bytes=body.chunk_bytes,
        chunk_count=body.chunk_count,
        received_chunks=received,
        missing_chunks=[index for index in range(body.chunk_count) if index not in present],
        state="COMPLETE" if row.dataset_id else "UPLOADING",
        dataset_id=row.dataset_id,
    )


def _declaration_identity(body: UploadInput) -> str:
    return json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def start_upload(db: Database, body: UploadInput) -> UploadView:
    """Bind an explicit idempotency key to one immutable upload declaration."""
    settings = get_settings()
    if body.chunk_bytes > settings.upload_max_chunk_bytes:
        message = "Declared chunk size exceeds upload_max_chunk_bytes"
        raise ValidationError(message)
    if body.total_bytes > settings.upload_max_file_bytes:
        message = "Declared file size exceeds upload_max_file_bytes"
        raise ValidationError(message)
    with response_lock(db, f"upload-create:{body.idempotency_key}"), db.session() as session:
        db.lock_writes(session)
        row = session.scalar(
            select(UploadRow).where(UploadRow.idempotency_key == body.idempotency_key)
        )
        if row is None:
            row = UploadRow(
                idempotency_key=body.idempotency_key, declaration=body.model_dump(mode="json")
            )
            session.add(row)
            session.flush()
        elif _declaration_identity(
            UploadInput.model_validate(row.declaration)
        ) != _declaration_identity(body):
            message = "Upload idempotency key is bound to another declaration"
            raise ConflictError(message)
        result = _view(row)
        session.commit()
        return result


def get_upload(db: Database, identifier: str) -> UploadView:
    """Resume from the durable missing-chunk receipt after connection or process loss."""
    with db.session() as session:
        return _view(_require(session, identifier))


def put_chunk(db: Database, identifier: str, ordinal: int, content: bytes) -> UploadView:
    """Serialize same-file writers; merge exact duplicates and refuse conflicting chunks."""
    with response_lock(db, f"upload:{identifier}"), db.session() as session:
        row = _require(session, identifier)
        if row.dataset_id:
            message = "Completed upload is immutable"
            raise ConflictError(message)
        body = UploadInput.model_validate(row.declaration)
        if len(content) != expected_bytes(body, ordinal):
            message = "Chunk byte count does not match its declared ordinal"
            raise ValidationError(message)
        persist_chunk(identifier, ordinal, content)
        return _view(row)


def complete_upload(db: Database, identifier: str) -> UploadView:
    """Hash the assembled file and actual object before publishing one atomic dataset."""
    with response_lock(db, f"upload:{identifier}"), db.session() as session:
        db.lock_writes(session)
        row = _require(session, identifier)
        if row.dataset_id:
            return _view(row)
        body = UploadInput.model_validate(row.declaration)
        with tempfile.TemporaryDirectory(prefix="datakeel-upload-") as directory:
            target = Path(directory) / body.filename
            assemble_file(identifier, body, target)
            dataset = import_dataset(session, body.name, [target], body.metadata)
            key = str(dataset.files[0]["metadata"]["object_key"])
            verify_stored_object(object_store(), key, body)
        row.dataset_id = dataset.id
        result = _view(row)
        session.commit()
        return result
