# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hold a real upload writer lock until the parent injects a process crash."""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from sqlalchemy import event

from datakeel.core.models import BoundaryModel
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.database import Database
from datakeel.storage.upload_files import upload_directory

if TYPE_CHECKING:
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry


class UploadProcessInput(BoundaryModel):
    """Point a child only to generated local state and the parent's isolated schema."""

    database_url: str
    schema_name: str | None = Field(default=None, pattern=r"^test_[0-9a-f]{32}$")
    identifier: str
    marker: Path


def main() -> None:
    """Leave an interrupted temporary while preserving exclusive writer ownership."""
    request = UploadProcessInput.model_validate_json(Path(sys.argv[1]).read_text())
    db = Database(request.database_url)
    if not db.sqlite:
        assert db.engine.url.host in {"localhost", "127.0.0.1"}
        assert request.schema_name is not None

        @event.listens_for(db.engine, "connect")
        def set_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{request.schema_name}"')
            connection.commit()
            cursor.close()

    with response_lock(db, f"upload:{request.identifier}"):
        directory = upload_directory(request.identifier)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "interrupted-temporary").write_bytes(b"partial")
        request.marker.write_text("locked")
        signal.pause()


if __name__ == "__main__":
    main()
