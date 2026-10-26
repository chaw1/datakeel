# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upload writer ownership across operating-system processes and abrupt death."""

import os
import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep

import pytest
from sqlalchemy import text

from datakeel.core.errors import ConflictError
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database
from datakeel.storage.upload_service import complete_upload, get_upload, put_chunk, start_upload
from tests.storage.test_uploads import declaration
from tests.storage.upload_process import UploadProcessInput


def test_separate_process_upload_lock_and_crash_resume(db: Database, tmp_path: Path) -> None:
    """Only one process writes; death releases ownership and partial files are not receipts."""
    upload = start_upload(db, declaration(b"abcd"))
    with db.session() as session:
        schema = None if db.sqlite else str(session.scalar(text("SELECT current_schema()")))
    request = UploadProcessInput(
        database_url=db.engine.url.render_as_string(hide_password=False),
        schema_name=schema,
        identifier=upload.id,
        marker=tmp_path / "upload-locked.marker",
    )
    path = tmp_path / "upload-process.request.json"
    path.write_text(request.model_dump_json())
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_", "LANGSMITH_"))
    }
    environment["DATAKEEL_HOME"] = str(get_settings().home)
    with subprocess.Popen(  # noqa: S603  # Fixed test helper and generated private local input.
        [sys.executable, "-m", "tests.storage.upload_process", str(path)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        try:
            deadline = monotonic() + 10
            while not request.marker.exists() and monotonic() < deadline and process.poll() is None:
                sleep(0.02)
            assert request.marker.exists()
            with pytest.raises(ConflictError):
                put_chunk(db, upload.id, 0, b"abcd")
            assert get_upload(db, upload.id).missing_chunks == [0]
        finally:
            process.kill()
            process.wait(timeout=10)
    assert put_chunk(db, upload.id, 0, b"abcd").missing_chunks == []
    assert complete_upload(db, upload.id).state == "COMPLETE"
