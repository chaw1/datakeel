# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional memory writes, scoped projections, reinforcement and hard deletion."""

from datetime import datetime
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.memory_models import (
    MemoryCreate,
    MemoryDeletion,
    MemoryEntry,
    MemoryPolicy,
    MemorySelection,
    MemoryUseScope,
)
from datakeel.core.models import new_id
from datakeel.memory.consolidation import consolidate
from datakeel.memory.retrieval import refreshed, reinforced, select_entries
from datakeel.storage.conversation_rows import ConversationRow
from datakeel.storage.data_asset_context import visible_memories
from datakeel.storage.database import Database, DatasetRow
from datakeel.storage.memory_rows import MemoryAuditRow, MemoryRow, MemoryUseRow, MemoryWriteRow


def _lock(db: Database, session: Session) -> None:
    db.lock_writes(session)
    if not db.sqlite:
        session.execute(text("LOCK TABLE memories IN SHARE ROW EXCLUSIVE MODE"))


def _rows(session: Session) -> list[MemoryRow]:
    return list(session.scalars(select(MemoryRow).order_by(MemoryRow.id)))


def _read(row: MemoryRow, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    return refreshed(MemoryEntry.model_validate(row.payload), now, policy)


def _existing(session: Session, identifier: str) -> MemoryRow:
    row = session.get(MemoryRow, identifier)
    if row is None:
        msg = f"Memory not found: {identifier}"
        raise NotFoundError(msg)
    return row


def _validate_source(session: Session, request: MemoryCreate) -> None:
    if request.dataset_id is not None and session.get(DatasetRow, request.dataset_id) is None:
        msg = f"Dataset not found: {request.dataset_id}"
        raise NotFoundError(msg)
    if (
        request.source_conversation_id is not None
        and session.get(ConversationRow, request.source_conversation_id) is None
    ):
        msg = f"Conversation not found: {request.source_conversation_id}"
        raise NotFoundError(msg)


def _replay(session: Session, request: MemoryCreate, digest: str) -> MemoryRow | None:
    prior = session.get(MemoryWriteRow, request.idempotency_key)
    if prior is None:
        return None
    if prior.digest != digest:
        msg = "Memory idempotency key is bound to a different write"
        raise ConflictError(msg)
    row = session.get(MemoryRow, prior.memory_id)
    if row is None:
        msg = "The memory for this write was deleted"
        raise ConflictError(msg)
    return row


def _consolidate(session: Session, now: datetime, policy: MemoryPolicy) -> None:
    rows = {row.id: row for row in _rows(session)}
    entries = consolidate([_read(row, now, policy) for row in rows.values()], now, policy)
    representatives: dict[str, str] = {}
    for entry in entries:
        rows[entry.id].payload = entry.model_dump(mode="json")
        if not entry.archived:
            representatives.update(dict.fromkeys(entry.source_memory_ids, entry.id))
    for request in session.scalars(select(MemoryWriteRow)):
        request.memory_id = representatives.get(request.memory_id, request.memory_id)


def create(db: Database, request: MemoryCreate, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    """Commit a redacted write and deterministic retention under one collection lock."""
    digest = sha256(request.model_dump_json(exclude={"idempotency_key"}).encode()).hexdigest()
    with db.session() as session:
        _lock(db, session)
        previous = _replay(session, request, digest)
        if previous is not None:
            return _read(previous, now, policy)
        _validate_source(session, request)
        entry = MemoryEntry(
            id=new_id(),
            content=request.content,
            dataset_id=request.dataset_id,
            source_conversation_ids=[request.source_conversation_id]
            if request.source_conversation_id
            else [],
            created_at=now,
            reinforced_at=now,
        )
        session.add(MemoryRow(id=entry.id, payload=entry.model_dump(mode="json")))
        write = MemoryWriteRow(key=request.idempotency_key, digest=digest, memory_id=entry.id)
        session.add(write)
        session.flush()
        _consolidate(session, now, policy)
        result = _read(_existing(session, write.memory_id), now, policy)
        session.commit()
        return result


def list_entries(
    db: Database,
    dataset_id: str | None,
    now: datetime,
    policy: MemoryPolicy,
    *,
    include_archived: bool = False,
    record: bool = False,
) -> list[MemoryEntry]:
    """List global and optionally matching dataset memories with current strength."""
    with db.session() as session:
        entries = [_read(row, now, policy) for row in _rows(session)]
    selected = [
        item
        for item in entries
        if (include_archived or not item.archived)
        and (dataset_id is None or item.dataset_id in {None, dataset_id})
    ]
    return visible_memories(db, selected, record=record)


def get(db: Database, identifier: str, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    """Read one current entry or raise a typed not-found error after hard deletion."""
    with db.session() as session:
        result = _read(_existing(session, identifier), now, policy)
    if not visible_memories(db, [result], record=True):
        msg = "Memory source requires an active query grant; apply for access"
        raise AuthorizationError(msg)
    return result


def select_memories(
    db: Database, query: str, dataset_id: str | None, now: datetime, policy: MemoryPolicy
) -> MemorySelection:
    """Read a fresh scope snapshot without strengthening memories before a model attempt."""
    entries = list_entries(db, dataset_id, now, policy)
    return select_entries(
        [item for item in entries if item.dataset_id in {None, dataset_id}], query
    )


def _used_in_turn(session: Session, scope: MemoryUseScope | None, identifier: str) -> bool:
    if scope is None:
        return False
    key = (scope.root_conversation_id, scope.user_message_number, identifier)
    if session.get(MemoryUseRow, key) is not None:
        return True
    session.add(MemoryUseRow(**scope.model_dump(), memory_id=identifier))
    return False


def reinforce(
    db: Database,
    identifiers: list[str],
    now: datetime,
    policy: MemoryPolicy,
    scope: MemoryUseScope | None = None,
) -> None:
    """Atomically deduplicate question-scoped strength while refreshing every actual use."""
    if not identifiers:
        return
    with db.session() as session:
        _lock(db, session)
        for identifier in sorted(set(identifiers)):
            row = session.get(MemoryRow, identifier)
            if row is not None:
                entry = _read(row, now, policy)
                if not entry.archived:
                    if _used_in_turn(session, scope, identifier):
                        entry = entry.model_copy(update={"last_used_at": now})
                    else:
                        entry = reinforced(entry, now, policy)
                    row.payload = entry.model_dump(mode="json")
        session.commit()


def _deletion_ids(rows: dict[str, MemoryRow], identifier: str) -> set[str]:
    selected: set[str] = set()
    pending = [identifier]
    while pending:
        current = pending.pop()
        if current in selected or current not in rows:
            continue
        selected.add(current)
        entry = MemoryEntry.model_validate(rows[current].payload)
        pending.extend(
            source
            for source in entry.source_memory_ids
            if source in rows and MemoryEntry.model_validate(rows[source].payload).archived
        )
    return selected


def delete(db: Database, identifier: str, now: datetime) -> MemoryDeletion:
    """Hard-delete a representative and its archived sources, retaining content-free audit."""
    with db.session() as session:
        _lock(db, session)
        _existing(session, identifier)
        rows = {row.id: row for row in _rows(session)}
        identifiers = _deletion_ids(rows, identifier)
        for memory_id in sorted(identifiers):
            session.delete(rows[memory_id])
        audit = MemoryDeletion(
            id=new_id(), memory_id=identifier, deleted_ids=sorted(identifiers), created_at=now
        )
        session.add(MemoryAuditRow(id=audit.id, payload=audit.model_dump(mode="json")))
        session.commit()
        return audit


def list_audit(db: Database) -> list[MemoryDeletion]:
    """Read deletion evidence in creation order without exposing any deleted content."""
    with db.session() as session:
        audits = [
            MemoryDeletion.model_validate(row.payload)
            for row in session.scalars(select(MemoryAuditRow))
        ]
    return sorted(audits, key=lambda item: (item.created_at, item.id))
