# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional immutable documentation storage and version-aware history reads."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.datasheet_models import (
    DATASHEET_CHAPTERS,
    DatasheetChapter,
    DatasheetComparison,
    DatasheetDocument,
    DatasheetFact,
    DatasheetFactChange,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.datasheet_facts import require_version
from datakeel.storage.datasheet_rows import DatasheetRow


def _row(session: Session, document_id: str, *, lock: bool = False) -> DatasheetRow:
    statement = select(DatasheetRow).where(DatasheetRow.id == document_id)
    row = session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        msg = "Dataset documentation not found"
        raise NotFoundError(msg)
    return row


def _view(session: Session, row: DatasheetRow) -> DatasheetDocument:
    latest = session.scalar(
        select(VersionRow)
        .where(VersionRow.dataset_id == row.dataset_id)
        .order_by(VersionRow.created_at.desc(), VersionRow.id.desc())
        .limit(1)
    )
    document = DatasheetDocument.model_validate(row.payload)
    return document.model_copy(
        update={
            "published": row.published,
            "stale": latest is not None and latest.id != row.version_id,
        }
    )


def save_in_session(session: Session, document: DatasheetDocument) -> DatasheetDocument:
    """Write an unpublished immutable snapshot inside the caller's transaction."""
    document = DatasheetDocument.model_validate(document.model_dump())
    require_version(session, document.dataset_id, document.version_id)
    payload = document.model_dump(mode="json", exclude={"published", "stale"})
    previous = session.get(DatasheetRow, document.id)
    if previous is not None:
        if previous.payload != payload:
            msg = "Documentation identity already binds different immutable content"
            raise ConflictError(msg)
        return _view(session, previous)
    if document.published:
        msg = "New documentation must be an unpublished draft"
        raise ValidationError(msg)
    row = DatasheetRow(
        id=document.id,
        dataset_id=document.dataset_id,
        version_id=document.version_id,
        created_at=document.created_at.timestamp(),
        payload=payload,
        published=False,
    )
    session.add(row)
    session.flush()
    return _view(session, row)


def save_document(db: Database, document: DatasheetDocument) -> DatasheetDocument:
    """Atomically save one draft without altering an existing frozen document."""
    with db.session() as session:
        db.lock_writes(session)
        result = save_in_session(session, document)
        session.commit()
        return result


def get_document(db: Database, document_id: str) -> DatasheetDocument:
    """Read a frozen document with publication and current-version expiry overlays."""
    with db.session() as session:
        return _view(session, _row(session, document_id))


def list_documents(
    db: Database, dataset_id: str, version_id: str | None = None
) -> tuple[DatasheetDocument, ...]:
    """List a dataset's immutable documentation history, newest first."""
    with db.session() as session:
        require_dataset(session, dataset_id)
        statement = select(DatasheetRow).where(DatasheetRow.dataset_id == dataset_id)
        if version_id is not None:
            require_version(session, dataset_id, version_id)
            statement = statement.where(DatasheetRow.version_id == version_id)
        return tuple(
            _view(session, row)
            for row in session.scalars(
                statement.order_by(DatasheetRow.created_at.desc(), DatasheetRow.id.desc())
            )
        )


def publish_in_session(session: Session, document_id: str) -> DatasheetDocument:
    """Publish an existing frozen document in the owning controlled-action transaction."""
    row = _row(session, document_id, lock=True)
    row.published = True
    session.flush()
    return _view(session, row)


def _matching_key(fact: DatasheetFact, document: DatasheetDocument) -> tuple[str, str, str]:
    # Version-scoped facts keep their field across versions; other sources keep their own ID.
    scoped = fact.source_id in {document.version_id, document.dataset_id}
    return (fact.source_type, "" if scoped else fact.source_id, fact.field)


def _compare(before: DatasheetDocument, after: DatasheetDocument) -> DatasheetComparison:
    if before.dataset_id != after.dataset_id:
        msg = "Documentation comparisons require the same dataset"
        raise ValidationError(msg)
    left = {_matching_key(fact, before): fact for fact in before.facts}
    right = {_matching_key(fact, after): fact for fact in after.facts}
    changes: list[DatasheetFactChange] = []
    chapters: set[DatasheetChapter] = set()
    for key in sorted(left.keys() | right.keys()):
        previous, current = left.get(key), right.get(key)
        if previous is not None and current is not None and previous.value == current.value:
            continue
        fact = current if current is not None else left[key]
        changes.append(
            DatasheetFactChange(
                fact_id=fact.id,
                before=previous.value if previous is not None else None,
                after=current.value if current is not None else None,
                kind="added" if previous is None else "removed" if current is None else "changed",
            )
        )
        chapters.add(fact.chapter)
    return DatasheetComparison(
        before_id=before.id,
        after_id=after.id,
        changes=tuple(changes),
        changed_chapters=tuple(chapter for chapter in DATASHEET_CHAPTERS if chapter in chapters),
    )


def compare_documents(db: Database, before_id: str, after_id: str) -> DatasheetComparison:
    """Compare only saved fact values, independent of later metadata or review changes."""
    with db.session() as session:
        return _compare(
            _view(session, _row(session, before_id)), _view(session, _row(session, after_id))
        )
