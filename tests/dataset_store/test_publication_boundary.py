# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detached publication facts and rollback after the second durable write."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select

from datakeel.core.models import FileItem
from datakeel.core.uploads import UploadInput, UploadView
from datakeel.dataset_store import datasets, upload_service
from datakeel.dataset_store.rows import (
    DatasetRow,
    EventRow,
    FileDiscoveryRow,
    UploadRow,
    VersionRow,
)
from datakeel.dataset_store.upload_files import upload_directory
from datakeel.dataset_store.version_stream import dataset_settings
from datakeel.datasets.records import PublishedDataset
from datakeel.storage.objects import digest, object_store

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session, UOWTransaction

    from datakeel.core.models import LineageEvent
    from datakeel.storage.database import Database


def test_publication_returns_detached_frozen_facts(db: Database, tmp_path: Path) -> None:
    """An import can leave its session without returning an attached database record."""
    source = tmp_path / "sample.txt"
    source.write_bytes(b"generated dataset")
    with db.session() as session:
        result = datasets.import_dataset(session, "sample", [source])
        settings = dataset_settings(session, result.id)
        assert isinstance(result, PublishedDataset)
        assert result.id == settings.id
        assert result.files[0].sha256 == digest(source)
        session.commit()
    for model in (result, settings):
        with pytest.raises(ValidationError, match="frozen"):
            model.name = "changed"
        with pytest.raises(ValidationError, match="extra_forbidden"):
            type(model).model_validate({**model.model_dump(), "undeclared": True})


@pytest.mark.parametrize("one_shot", [False, True])
def test_publication_reuses_prepared_file_instances(
    db: Database, monkeypatch: pytest.MonkeyPatch, *, one_shot: bool
) -> None:
    """Tuple and single-pass inputs retain validated models without manifest reparsing."""
    items = tuple(FileItem(path="", filename=f"generated-{i}.txt") for i in range(3))

    def reject_reparse(_value: object) -> FileItem:
        pytest.fail("publication must reuse prepared FileItem instances")

    monkeypatch.setattr(FileItem, "model_validate", reject_reparse)
    with db.session() as session:
        result = datasets.publish_files(session, "reuse", iter(items) if one_shot else items)
        assert all(actual is prepared for actual, prepared in zip(result.files, items, strict=True))
        row = session.get(DatasetRow, result.id)
        assert row is not None
        assert row.files == [item.model_dump(mode="json") for item in items]
        session.commit()
    with pytest.raises(ValidationError, match="frozen"):
        result.files[0].filename = "changed.txt"


def _stage(db: Database) -> str:
    content = b"generated second-write rollback"
    body = UploadInput(
        idempotency_key="second-write",
        name="sample",
        filename="sample.txt",
        total_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        chunk_bytes=len(content),
    )
    upload = upload_service.start_upload(db, body)
    upload_service.put_chunk(db, upload.id, 0, content)
    return upload.id


@pytest.mark.parametrize("point", ["version", "lineage", "receipt"])
def test_second_write_failure_rolls_back_facts_and_retains_retry(
    db: Database, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    """Both CI stacks execute real SQL before failure; only a successful retry commits."""
    identifier = _stage(db)
    commits: list[Session] = []
    record_commit = commits.append
    original = datasets.append_event

    def fail_version(session: Session, _context: UOWTransaction) -> None:
        if point == "version" and session.scalar(select(func.count()).select_from(VersionRow)):
            assert session.scalar(select(func.count()).select_from(FileDiscoveryRow)) == 1
            msg = "after second write"
            raise RuntimeError(msg)

    def fail_lineage(session: Session, value: LineageEvent) -> bool:
        result = original(session, value)
        if point == "lineage":
            msg = "after second write"
            raise RuntimeError(msg)
        return result

    event.listen(db.sessions, "after_flush_postexec", fail_version)
    event.listen(db.sessions, "after_commit", record_commit)
    monkeypatch.setattr(datasets, "append_event", fail_lineage)
    try:
        _fail_completion(db, identifier, point, monkeypatch)
        assert commits == []
    finally:
        event.remove(db.sessions, "after_flush_postexec", fail_version)
        monkeypatch.setattr(datasets, "append_event", original)
    _assert_rolled_back(db, identifier)
    result = upload_service.complete_upload(db, identifier)
    assert result.state == "COMPLETE"
    assert len(commits) == 1
    event.remove(db.sessions, "after_commit", record_commit)
    assert not upload_directory(identifier).exists()
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 1
        value = session.scalar(select(EventRow))
        assert value is not None
        assert value.payload["source_module"] == "storage"


def _fail_completion(
    db: Database, identifier: str, point: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = upload_service._publish_upload  # noqa: SLF001  # Inject after receipt flush.

    def fail_receipt(
        session: Session, upload_id: str, body: UploadInput, files: tuple[FileItem, ...]
    ) -> UploadView:
        original(session, upload_id, body, files)
        session.flush()
        msg = "after second write"
        raise RuntimeError(msg)

    with monkeypatch.context() as patch:
        if point == "receipt":
            patch.setattr(upload_service, "_publish_upload", fail_receipt)
        with pytest.raises(RuntimeError, match="after second write"):
            upload_service.complete_upload(db, identifier)


def _assert_rolled_back(db: Database, identifier: str) -> None:
    with db.session() as session:
        for row_type in (DatasetRow, VersionRow, EventRow, FileDiscoveryRow):
            assert session.scalar(select(func.count()).select_from(row_type)) == 0
        upload = session.get(UploadRow, identifier)
        assert upload is not None
        assert upload.dataset_id is None
    assert upload_directory(identifier).is_dir()
    checksum = hashlib.sha256(b"generated second-write rollback").hexdigest()
    assert digest(object_store().materialize(f"{checksum[:2]}/{checksum}.txt")) == checksum
