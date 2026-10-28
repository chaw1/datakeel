# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upload integrity work stays outside database write transactions."""

import hashlib
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.core.uploads import UploadInput, UploadView
from datakeel.storage import upload_service
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.upload_files import upload_directory
from datakeel.storage.upload_rows import UploadRow


def _staged(db: Database) -> UploadView:
    content = b"generated upload"
    body = UploadInput(
        idempotency_key="short-transaction",
        name="Generated sample",
        filename="sample.txt",
        total_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        chunk_bytes=len(content),
    )
    upload = upload_service.start_upload(db, body)
    upload_service.put_chunk(db, upload.id, 0, content)
    return upload


def test_upload_assembly_allows_unrelated_writer_commit(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paused assembler must not hold SQLite's global writer slot or publish early."""
    upload = _staged(db)
    entered, release, writer_done = Event(), Event(), Event()
    original = upload_service.assemble_file

    def paused(identifier: str, body: UploadInput, target: Path) -> None:
        entered.set()
        if not release.wait(10):
            msg = "Upload assembly test was not released"
            raise AssertionError(msg)
        original(identifier, body, target)

    def write_other_dataset() -> None:
        with db.session() as session:
            db.lock_writes(session)
            session.add(DatasetRow(name="Independent writer", files=[]))
            session.commit()
        writer_done.set()

    monkeypatch.setattr(upload_service, "assemble_file", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        completed = pool.submit(upload_service.complete_upload, db, upload.id)
        try:
            assert entered.wait(10)
            with db.session() as session:
                row = session.get(UploadRow, upload.id)
                assert row is not None
                assert row.dataset_id is None
            writer = pool.submit(write_other_dataset)
            committed_while_paused = writer_done.wait(1)
        finally:
            release.set()
        receipt = completed.result(timeout=10)
        writer.result(timeout=10)
    assert committed_while_paused
    assert receipt.state == "COMPLETE"


def test_upload_changed_declaration_cannot_publish_after_preparation(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The final short transaction revalidates the declaration it originally verified."""
    upload = _staged(db)
    original = upload_service.assemble_file

    def change_declaration(identifier: str, body: UploadInput, target: Path) -> None:
        original(identifier, body, target)
        with db.session() as session:
            row = session.get(UploadRow, identifier)
            assert row is not None
            row.declaration = {**row.declaration, "name": "Changed while preparing"}
            session.commit()

    monkeypatch.setattr(upload_service, "assemble_file", change_declaration)
    with pytest.raises(ConflictError, match="declaration"):
        upload_service.complete_upload(db, upload.id)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(DatasetRow)) == 0
    assert upload_directory(upload.id).is_dir()


def test_upload_publication_failure_rolls_back_dataset_and_receipt(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure after manifest flush cannot commit a dataset without its upload receipt."""
    upload = _staged(db)
    original = upload_service.publish_files

    def failed_publish(
        session: Session,
        name: str,
        files: Sequence[FileItem],
        metadata: JsonDocument | None = None,
    ) -> DatasetRow:
        original(session, name, files, metadata)
        msg = "Injected failure after dataset publication"
        raise RuntimeError(msg)

    monkeypatch.setattr(upload_service, "publish_files", failed_publish)
    with pytest.raises(RuntimeError, match="Injected failure"):
        upload_service.complete_upload(db, upload.id)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(DatasetRow)) == 0
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 0
        row = session.get(UploadRow, upload.id)
        assert row is not None
        assert row.dataset_id is None
    assert upload_directory(upload.id).is_dir()
    monkeypatch.setattr(upload_service, "publish_files", original)
    assert upload_service.complete_upload(db, upload.id).state == "COMPLETE"
