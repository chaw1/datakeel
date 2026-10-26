# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded upload staging and independent stored-object verification."""

import hashlib
import shutil
import tempfile
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.settings import get_settings
from datakeel.core.uploads import UploadInput
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.database import Database, data_dir
from datakeel.storage.objects import ObjectStore, digest, fresh_object


def upload_directory(identifier: str) -> Path:
    """Resolve an already validated database identifier under the private staging root."""
    return data_dir() / "uploads" / identifier


def received_chunks(identifier: str, body: UploadInput) -> list[int]:
    """Inspect only atomically committed chunk files, ignoring interrupted temporaries."""
    directory = upload_directory(identifier)
    return [index for index in range(body.chunk_count) if (directory / str(index)).is_file()]


def expected_bytes(body: UploadInput, ordinal: int) -> int:
    """Reject invalid ordinals and compute the exact final-chunk size."""
    if ordinal < 0 or ordinal >= body.chunk_count:
        message = "Chunk ordinal is outside the declared file"
        raise ValidationError(message)
    return min(body.chunk_bytes, body.total_bytes - ordinal * body.chunk_bytes)


def persist_chunk(identifier: str, ordinal: int, content: bytes) -> None:
    """Accept identical retries and refuse conflicting retries without replacing bytes."""
    directory = upload_directory(identifier)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / str(ordinal)
    if destination.exists():
        if digest(destination) != hashlib.sha256(content).hexdigest():
            message = "Chunk already exists with different content"
            raise ConflictError(message)
        return
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(content)
            temporary.flush()
            path.replace(destination)
        finally:
            path.unlink(missing_ok=True)


def assemble_file(identifier: str, body: UploadInput, target: Path) -> None:
    """Join chunks in declared ordinal order with constant-size copy buffers."""
    directory = upload_directory(identifier)
    with target.open("wb") as output:
        for ordinal in range(body.chunk_count):
            chunk = directory / str(ordinal)
            if not chunk.is_file() or chunk.stat().st_size != expected_bytes(body, ordinal):
                message = f"Missing or incorrectly sized chunk: {ordinal}"
                raise ValidationError(message)
            with chunk.open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    if target.stat().st_size != body.total_bytes or digest(target) != body.sha256:
        message = "Whole-file SHA-256 or byte count mismatch; dataset was not published"
        raise ValidationError(message)


def verify_stored_object(store: ObjectStore, key: str, body: UploadInput) -> None:
    """Read actual stored bytes, bypassing S3 caches, before committing any dataset."""
    try:
        with fresh_object(store, key) as path:
            if path.stat().st_size != body.total_bytes or digest(path) != body.sha256:
                message = "Stored object SHA-256 or byte count mismatch; dataset was not published"
                raise ValidationError(message)
    except FileNotFoundError as error:
        message = "Stored object is missing; dataset was not published"
        raise ValidationError(message) from error


@contextmanager
def upload_slot(db: Database) -> Generator[None]:
    """Bound concurrent chunk streams across processes using crash-released shared locks."""
    for ordinal in range(get_settings().upload_max_concurrency):
        stack = ExitStack()
        try:
            stack.enter_context(response_lock(db, f"upload-slot:{ordinal}"))
        except ConflictError:
            stack.close()
            continue
        with stack:
            yield
        return
    message = "Upload concurrency limit reached; retry after an active chunk completes"
    raise ConflictError(message)
