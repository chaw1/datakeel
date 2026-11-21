# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional memory writes, scoped projections, reinforcement and hard deletion."""

from datetime import datetime
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.actions.registry import action_definition
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.memory_models import (
    MemoryCreate,
    MemoryDeletion,
    MemoryEntry,
    MemoryPolicy,
    MemoryReadOptions,
    MemorySelection,
    MemoryUseScope,
)
from datakeel.core.models import new_id
from datakeel.dataset_store.rows import DatasetRow
from datakeel.memory.consolidation import consolidate, deletion_ids
from datakeel.memory.retrieval import refreshed, reinforced, select_entries
from datakeel.storage.conversation_rows import ConversationRow
from datakeel.storage.data_asset_context import visible_memories
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.memory_rows import MemoryAuditRow, MemoryRow, MemoryUseRow, MemoryWriteRow


def _lock(db: Database, session: Session) -> None:
    db.lock_writes(session)
    if not db.sqlite:
        session.execute(text("LOCK TABLE memories IN SHARE ROW EXCLUSIVE MODE"))


def _rows(session: Session) -> list[MemoryRow]:
    return list(session.scalars(select(MemoryRow).order_by(MemoryRow.id)))


def _read(row: MemoryRow, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    return refreshed(MemoryEntry.model_validate(row.payload), now, policy)


def _existing(session: Session, identifier: str, *, active: bool = False) -> MemoryRow:
    row = session.get(MemoryRow, identifier)
    if row is None or (active and MemoryEntry.model_validate(row.payload).archived):
        msg = f"Memory not found: {identifier}"
        raise NotFoundError(msg)
    return row


def _require_write_scope(session: Session, actor: str) -> None:
    scope = action_definition("manage_users").auth_scope
    if not {"*", scope}.intersection(effective_scopes(session, actor).scopes):
        msg = f"Memory writes require a server-authorized action scope: {scope}"
        raise AuthorizationError(msg)


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
    representatives: dict[str, str] = {}
    for entry in consolidate([_read(row, now, policy) for row in rows.values()], now, policy):
        rows[entry.id].payload = entry.model_dump(mode="json")
        if not entry.archived:
            representatives.update(dict.fromkeys(entry.source_memory_ids, entry.id))
    for request in session.scalars(select(MemoryWriteRow)):
        request.memory_id = representatives.get(request.memory_id, request.memory_id)


def create(
    db: Database,
    request: MemoryCreate,
    now: datetime,
    policy: MemoryPolicy,
    *,
    actor: str = "local",
) -> MemoryEntry:
    """Commit a redacted write and deterministic retention under one collection lock."""
    digest = sha256(request.model_dump_json(exclude={"idempotency_key"}).encode()).hexdigest()
    with db.session() as session:
        _lock(db, session)
        _require_write_scope(session, actor)
        if (previous := _replay(session, request, digest)) is not None:
            return _read(previous, now, policy)
        for model, identifier, label in (
            (DatasetRow, request.dataset_id, "Dataset"),
            (ConversationRow, request.source_conversation_id, "Conversation"),
        ):
            if identifier is not None and session.get(model, identifier) is None:
                msg = f"{label} not found: {identifier}"
                raise NotFoundError(msg)
        source = request.source_conversation_id
        entry = MemoryEntry(
            id=new_id(),
            content=request.content,
            dataset_id=request.dataset_id,
            source_conversation_ids=[source] if source else [],
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
    options: MemoryReadOptions | None = None,
) -> list[MemoryEntry]:
    """List global and optionally matching dataset memories with current strength."""
    with db.session() as session:
        entries = [_read(row, now, policy) for row in _rows(session)]
    options = options or MemoryReadOptions()
    selected = [
        item
        for item in entries
        if (options.include_archived or not item.archived)
        and (dataset_id is None or item.dataset_id in {None, dataset_id})
    ]
    return visible_memories(db, selected, record=options.record, actor=options.actor)


def get(
    db: Database, identifier: str, now: datetime, policy: MemoryPolicy, *, actor: str = "local"
) -> MemoryEntry:
    """Read one current entry or raise a typed not-found error after hard deletion."""
    with db.session() as session:
        result = _read(_existing(session, identifier), now, policy)
    if not visible_memories(db, [result], record=True, actor=actor):
        msg = "Memory source requires an active query grant; apply for access"
        raise AuthorizationError(msg)
    return result


def select_memories(
    db: Database,
    query: str,
    dataset_id: str | None,
    now: datetime,
    policy: MemoryPolicy,
    *,
    actor: str = "local",
) -> MemorySelection:
    """Read a fresh scope snapshot without strengthening memories before a model attempt."""
    entries = list_entries(db, dataset_id, now, policy, options=MemoryReadOptions(actor=actor))
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


def delete(db: Database, identifier: str, now: datetime) -> MemoryDeletion:
    """Hard-delete a representative and its archived sources, retaining content-free audit."""
    with db.session() as session:
        _lock(db, session)
        _existing(session, identifier)
        rows = {row.id: row for row in _rows(session)}
        entries = [MemoryEntry.model_validate(row.payload) for row in rows.values()]
        identifiers = deletion_ids(entries, identifier)
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


def update(
    db: Database,
    identifier: str,
    content: str,
    now: datetime,
    policy: MemoryPolicy,
    *,
    actor: str = "local",
) -> MemoryEntry:
    """Replace active memory content under the same write scope and source visibility guards."""
    with db.session() as session:
        _lock(db, session)
        _require_write_scope(session, actor)
        row = _existing(session, identifier, active=True)
        entry = _read(row, now, policy)
        if not visible_memories(db, [entry], actor=actor):
            msg = "Memory source requires an active query grant; apply for access"
            raise AuthorizationError(msg)
        entry = entry.model_copy(update={"content": content})
        row.payload = entry.model_dump(mode="json")
        session.commit()
        return entry
