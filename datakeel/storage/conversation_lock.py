# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Process-released conversation locks protect response leases across crashes."""

import fcntl
import hashlib
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import text

from datakeel.core.errors import ConflictError
from datakeel.storage.database import Database, data_dir

_BUSY = "Conversation already has an active response"


@contextmanager
def response_lock(
    db: Database, conversation_id: str, *, busy_message: str = _BUSY
) -> Generator[None]:
    """Reject overlapping writers; let the operating system release ownership after SIGKILL."""
    if db.sqlite:
        with _sqlite_lock(db, conversation_id, busy_message):
            yield
        return
    with db.engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(current_schema()), hashtext(:identity))"),
            {"identity": f"datakeel:conversation:{conversation_id}"},
        )
        connection.commit()
        if not acquired:
            raise ConflictError(busy_message)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(current_schema()), hashtext(:identity))"),
                {"identity": f"datakeel:conversation:{conversation_id}"},
            )
            connection.commit()


@contextmanager
def _sqlite_lock(db: Database, conversation_id: str, busy_message: str) -> Generator[None]:
    database = Path(db.engine.url.database or data_dir() / "memory.db").resolve()
    directory = database.parent / f".{database.name}.response-locks"
    directory.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(conversation_id.encode()).hexdigest()
    # Keep the inode stable: unlinking lock files could create two simultaneous owners.
    with (directory / filename).open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ConflictError(busy_message) from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
