# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish and retrieve independently frozen, append-only dataset releases."""

from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.release_models import (
    ReleaseFile,
    ReleaseFiles,
    ReleaseView,
    StoredReleaseFile,
    VersionSummary,
)
from datakeel.storage.database import Database
from datakeel.storage.release_rows import ReleaseEntryRow, ReleaseRow
from datakeel.storage.version_stream import dataset_settings

MAX_PAGE = 1000


def release_view(row: ReleaseRow) -> ReleaseView:
    """Validate a header without exposing persistence rows to application callers."""
    return ReleaseView(
        id=row.id,
        dataset_id=row.dataset_id,
        version_id=row.version_id,
        tag=row.tag,
        notes=row.notes,
        created_at=row.created_at,
        manifest_sha256=row.manifest_sha256,
        file_count=row.file_count,
        total_bytes=row.total_bytes,
        metadata=row.metadata_values,
        summary=VersionSummary.model_validate(row.summary),
    )


def require_release(session: Session, identifier: str) -> ReleaseView:
    """Resolve and validate a frozen header inside a caller-owned transaction."""
    row = session.get(ReleaseRow, identifier)
    if row is None:
        message = "Release not found"
        raise NotFoundError(message)
    return release_view(row)


def get_release(db: Database, identifier: str) -> ReleaseView:
    """Read one immutable published release."""
    with db.session() as session:
        return require_release(session, identifier)


def list_releases(db: Database, dataset_id: str) -> list[ReleaseView]:
    """List publication headers for an existing dataset in creation order."""
    with db.session() as session:
        dataset_settings(session, dataset_id)
        return [
            release_view(row)
            for row in session.scalars(
                select(ReleaseRow)
                .where(ReleaseRow.dataset_id == dataset_id)
                .order_by(ReleaseRow.created_at, ReleaseRow.id)
            )
        ]


def iter_release_entries(session: Session, release_id: str) -> Iterator[StoredReleaseFile]:
    """Stream frozen public facts plus private object keys for trusted delivery services."""
    require_release(session, release_id)
    rows = session.scalars(
        select(ReleaseEntryRow)
        .where(ReleaseEntryRow.release_id == release_id)
        .order_by(ReleaseEntryRow.ordinal)
    ).yield_per(100)
    for row in rows:
        yield StoredReleaseFile(
            file=ReleaseFile.model_validate(row.record), object_key=row.object_key
        )


def list_release_files(
    db: Database, identifier: str, offset: int = 0, limit: int = 100
) -> ReleaseFiles:
    """Page through immutable entries without loading the entire publication."""
    if offset < 0 or not 1 <= limit <= MAX_PAGE:
        message = "Release offset must be nonnegative and limit must be between 1 and 1000"
        raise ValidationError(message)
    with db.session() as session:
        require_release(session, identifier)
        rows = session.scalars(
            select(ReleaseEntryRow)
            .where(ReleaseEntryRow.release_id == identifier)
            .order_by(ReleaseEntryRow.ordinal)
            .offset(offset)
            .limit(limit + 1)
        )
        files = [ReleaseFile.model_validate(row.record) for row in rows]
        return ReleaseFiles(
            files=files[:limit], next_offset=offset + limit if len(files) > limit else None
        )
