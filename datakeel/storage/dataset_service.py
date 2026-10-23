# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset transactions and validated projections for application callers."""

import base64
import binascii
import tempfile
from pathlib import Path

from pydantic import Field, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import FileItem
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.datasets import dataset_dict, import_dataset
from datakeel.storage.file_state import FileStateRow, get_file_state, overlay_files
from datakeel.storage.objects import object_store
from datakeel.storage.views import DatasetView, DownloadView, FileView, VersionView, View


class UploadFile(View):
    """One basename and base64-encoded upload payload."""

    filename: str
    content_base64: str


class DatasetInput(View):
    """A local dataset import request."""

    name: str = Field(min_length=1, max_length=200)
    files: list[UploadFile] = Field(default_factory=list[UploadFile], max_length=1000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def require_dataset(session: Session, identifier: str, *, lock: bool = False) -> DatasetRow:
    """Resolve a dataset inside an existing storage transaction."""
    statement = select(DatasetRow).where(DatasetRow.id == identifier)
    row = session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        message = "Dataset not found"
        raise NotFoundError(message)
    return row


def public_files(values: list[dict[str, JsonValue]]) -> list[FileView]:
    """Validate manifest records after excluding private paths."""
    return [
        FileView.model_validate({k: v for k, v in item.items() if k != "path"}) for item in values
    ]


def _dataset_view(session: Session, row: DatasetRow) -> DatasetView:
    result = DatasetView.model_validate(dataset_dict(row))
    deleted = set(
        session.scalars(
            select(FileStateRow.file_id).where(
                FileStateRow.dataset_id == row.id,
                FileStateRow.deleted.is_(True),
            )
        )
    )
    return result.model_copy(
        update={
            "file_count": sum(str(item["id"]) not in deleted for item in row.files),
        }
    )


def list_datasets(db: Database) -> list[DatasetView]:
    """List dataset summaries in creation order."""
    with db.session() as session:
        return [
            _dataset_view(session, row)
            for row in session.scalars(select(DatasetRow).order_by(DatasetRow.created_at))
        ]


def get_dataset(db: Database, identifier: str) -> DatasetView:
    """Return a dataset summary or a domain missing-resource error."""
    with db.session() as session:
        return _dataset_view(session, require_dataset(session, identifier))


def _write_upload(item: UploadFile, directory: Path) -> Path:
    if Path(item.filename).name != item.filename or not item.filename or "\\" in item.filename:
        message = "Filename must be a plain basename"
        raise ValidationError(message)
    directory.mkdir()
    path = directory / item.filename
    try:
        path.write_bytes(base64.b64decode(item.content_base64, validate=True))
    except binascii.Error as exc:
        message = "Invalid base64 content"
        raise ValidationError(message) from exc
    return path


def create_dataset(db: Database, body: DatasetInput) -> DatasetView:
    """Persist uploaded objects and atomically publish the first manifest."""
    with tempfile.TemporaryDirectory(prefix="datakeel-import-") as temporary:
        paths = [
            _write_upload(item, Path(temporary) / str(index))
            for index, item in enumerate(body.files)
        ]
        with db.session() as session:
            row = import_dataset(session, body.name, paths, body.metadata)
            result = DatasetView.model_validate(dataset_dict(row))
            session.commit()
            return result


def list_files(db: Database, identifier: str, version: str | None = None) -> list[FileView]:
    """List original files or a selected immutable version."""
    with db.session() as session:
        values = require_dataset(session, identifier).files
        if version:
            record = session.get(VersionRow, version)
            if record is None or record.dataset_id != identifier:
                message = "Version not found"
                raise NotFoundError(message)
            values = record.manifest
        visible = overlay_files(
            session, identifier, [FileItem.model_validate(item) for item in values]
        )
        return public_files([item.model_dump(mode="json") for item in visible])


def list_versions(db: Database, identifier: str) -> list[VersionView]:
    """List all immutable snapshots belonging to a dataset."""
    with db.session() as session:
        require_dataset(session, identifier)
        return [
            VersionView(
                id=row.id,
                created_at=row.created_at,
                file_count=len(row.manifest),
                manifest=public_files(row.manifest),
            )
            for row in session.scalars(
                select(VersionRow)
                .where(VersionRow.dataset_id == identifier)
                .order_by(VersionRow.created_at)
            )
        ]


def resolve_download(
    db: Database, identifier: str, file_id: str, version: str | None = None
) -> DownloadView:
    """Resolve a public file, preserving exact version ownership when explicitly pinned."""
    with db.session() as session:
        dataset = require_dataset(session, identifier)
        if version is not None:
            manifest = session.get(VersionRow, version)
            if manifest is None or manifest.dataset_id != identifier:
                message = "Version not found"
                raise NotFoundError(message)
            candidates = manifest.manifest
        else:
            candidates = dataset.files + [
                item
                for stored in session.scalars(
                    select(VersionRow).where(VersionRow.dataset_id == identifier)
                )
                for item in stored.manifest
            ]
        record = next((item for item in candidates if item["id"] == file_id), None)
        if record is None or get_file_state(session, identifier, file_id).deleted:
            message = "File not found"
            raise NotFoundError(message)
        value = FileView.model_validate({k: v for k, v in record.items() if k != "path"})
        key = value.metadata.get("object_key")
        if not isinstance(key, str):
            message = "File object not found"
            raise NotFoundError(message)
        return DownloadView(path=object_store().materialize(key), filename=value.filename)


def task_artifacts(db: Database, identifier: str) -> list[FileView]:
    """Return published artifacts of a completed task."""
    with db.session() as session:
        row = session.scalar(select(VersionRow).where(VersionRow.task_id == identifier))
        if row is None:
            message = "Completed artifacts not found"
            raise NotFoundError(message)
        return public_files(row.manifest)


def import_paths(
    db: Database, name: str, paths: list[Path], metadata: dict[str, JsonValue] | None = None
) -> DatasetView:
    """Import local paths and return a validated summary after atomic publication."""
    with db.session() as session:
        row = import_dataset(session, name, paths, metadata)
        result = DatasetView.model_validate(dataset_dict(row))
        session.commit()
        return result
