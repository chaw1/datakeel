# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read legacy JSON manifests one entry at a time without materializing their arrays."""

import json
from collections.abc import Iterator

from sqlalchemy import select, text
from sqlalchemy.orm import Session, defer

from datakeel.core.errors import ConflictError, ExecutionError, NotFoundError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.core.portable_metadata import portable_metadata
from datakeel.core.release_models import ReleaseFile, annotation_statistics
from datakeel.storage.database import DatasetRow, VersionRow


def require_version(
    session: Session, dataset_id: str, version_id: str, *, lock: bool = False
) -> None:
    """Check exact version ownership without selecting the JSON manifest column."""
    statement = select(VersionRow.id).where(
        VersionRow.dataset_id == dataset_id, VersionRow.id == version_id
    )
    found = session.scalar(statement.with_for_update() if lock else statement)
    if found is None:
        message = "Version not found in this dataset"
        raise NotFoundError(message)


def stream_manifest(session: Session, version_id: str) -> Iterator[FileItem]:
    """Stream file records in code-point identity order using database JSON expansion.

    The comparison merge and release ordinals use Python string order. PostgreSQL would
    otherwise sort by the database collation (ICU or glibc locales order mixed case and
    punctuation differently), so its sort is pinned to "C": byte order of UTF-8 equals
    code-point order. SQLite's default BINARY collation already compares bytes.
    """
    sqlite = session.get_bind().dialect.name == "sqlite"
    statement = (
        "SELECT value FROM versions, json_each(versions.manifest) "
        "WHERE versions.id = :version ORDER BY json_extract(value, '$.id')"
        if sqlite
        else "SELECT value FROM versions, json_array_elements(versions.manifest) AS value "
        "WHERE versions.id = :version ORDER BY value->>'id' COLLATE \"C\""
    )
    result = session.execute(
        text(statement).execution_options(yield_per=100), {"version": version_id}
    )
    yield from ordered_identities(
        FileItem.model_validate(json.loads(row[0]) if isinstance(row[0], str) else row[0])
        for row in result
    )


def ordered_identities(items: Iterator[FileItem]) -> Iterator[FileItem]:
    """Yield strictly increasing file identities, refusing duplicates and misordered streams."""
    previous: str | None = None
    for item in items:
        if previous is not None and item.id == previous:
            message = "Version contains duplicate file identities"
            raise ConflictError(message)
        if previous is not None and item.id < previous:
            message = (
                "Version manifest stream is not in code-point order of file identities; "
                "comparison stopped instead of misaligning files"
            )
            raise ExecutionError(message)
        previous = item.id
        yield item


def portable_file(item: FileItem, version_id: str) -> ReleaseFile:
    """Exclude physical locations from the portable release and comparison boundary."""
    metadata = JsonDocument.model_validate(item.metadata).root
    metadata = portable_metadata(metadata)
    annotations, labels = annotation_statistics(metadata)
    return ReleaseFile(
        id=item.id,
        filename=item.filename,
        sha256=item.sha256,
        size=item.size,
        modality=item.modality,
        metadata=metadata,
        source_version=version_id,
        lineage_refs=(version_id,),
        annotation_count=annotations,
        label_count=labels,
    )


def dataset_settings(session: Session, dataset_id: str) -> DatasetRow:
    """Read governance settings while deferring the large original dataset manifest."""
    row = session.scalar(
        select(DatasetRow).options(defer(DatasetRow.files)).where(DatasetRow.id == dataset_id)
    )
    if row is None:
        message = "Dataset not found"
        raise NotFoundError(message)
    return row
