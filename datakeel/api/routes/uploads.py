# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded binary chunk streams and resumable upload publication."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.core.uploads import UploadInput, UploadView
from datakeel.storage import upload_service as service
from datakeel.storage.upload_files import upload_slot

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("", status_code=201)
def start(body: UploadInput, db: DatabaseDependency) -> UploadView:
    """Declare file size, SHA-256, chunk size and a reusable idempotency key."""
    return service.start_upload(db, body)


@router.get("/{identifier}")
def status(identifier: str, db: DatabaseDependency) -> UploadView:
    """Read missing ordinals so reconnection sends only absent chunks."""
    return service.get_upload(db, identifier)


@router.put(
    "/{identifier}/chunks/{ordinal}",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def chunk(
    identifier: str, ordinal: int, request: Request, db: DatabaseDependency
) -> UploadView:
    """Stream at most the configured chunk limit under a process-shared concurrency cap."""
    with upload_slot(db):
        service.get_upload(db, identifier)
        content = bytearray()
        limit = get_settings().upload_max_chunk_bytes
        async for part in request.stream():
            if len(content) + len(part) > limit:
                message = "Chunk exceeds upload_max_chunk_bytes"
                raise ValidationError(message)
            content.extend(part)
        return service.put_chunk(db, identifier, ordinal, bytes(content))


@router.post("/{identifier}/complete")
def complete(identifier: str, db: DatabaseDependency) -> UploadView:
    """Verify every chunk and both whole-file hashes before atomic dataset publication."""
    with upload_slot(db):
        return service.complete_upload(db, identifier)
