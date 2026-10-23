# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Opaque, typed checkpoint persistence independent of graph frameworks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from sqlalchemy import Integer, LargeBinary, String, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import BoundaryModel
from datakeel.storage.base import Base

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from datakeel.storage.database import Database


class CheckpointKey(BoundaryModel):
    """Identify a snapshot within an independent conversation namespace."""

    thread_id: str
    checkpoint_ns: str = ""
    checkpoint_id: str


class CheckpointWrite(BoundaryModel):
    """Carry a serialized write without exposing framework or row objects."""

    task_id: str
    idx: int
    channel: str
    value: bytes
    task_path: str = ""


class CheckpointRecord(BoundaryModel):
    """Keep a complete serialized snapshot and its ordered pending writes."""

    key: CheckpointKey
    checkpoint: bytes
    metadata: bytes
    parent_checkpoint_id: str | None = None
    writes: list[CheckpointWrite] = Field(default_factory=list[CheckpointWrite])


class CheckpointQuery(BoundaryModel):
    """Restrict opaque snapshots without interpreting their serialized metadata."""

    thread_id: str | None = None
    checkpoint_ns: str | None = None
    checkpoint_id: str | None = None
    before: str | None = None
    limit: int | None = Field(default=None, ge=0)


class CheckpointRow(Base):
    """Store binary snapshots without database JSON encoding constraints."""

    __tablename__ = "checkpoints"
    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String, nullable=True)
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_bytes: Mapped[bytes] = mapped_column(LargeBinary)


class CheckpointWriteRow(Base):
    """Deduplicate task writes while allowing replacement of special indices."""

    __tablename__ = "checkpoint_writes"
    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_path: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String)
    value: Mapped[bytes] = mapped_column(LargeBinary)


def put_checkpoint(db: Database, record: CheckpointRecord) -> None:
    """Atomically insert or replace one fully serialized snapshot."""
    factory = sqlite_insert if db.sqlite else pg_insert
    statement = factory(CheckpointRow).values(
        **record.key.model_dump(),
        checkpoint=record.checkpoint,
        metadata_bytes=record.metadata,
        parent_checkpoint_id=record.parent_checkpoint_id,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["thread_id", "checkpoint_ns", "checkpoint_id"],
        set_={
            "checkpoint": statement.excluded.checkpoint,
            "metadata_bytes": statement.excluded.metadata_bytes,
            "parent_checkpoint_id": statement.excluded.parent_checkpoint_id,
        },
    )
    with db.session() as session:
        db.lock_writes(session)
        session.execute(statement)
        session.commit()


def put_writes(db: Database, key: CheckpointKey, writes: Sequence[CheckpointWrite]) -> None:
    """Retain first ordinary writes and replace negative-index control writes."""
    factory = sqlite_insert if db.sqlite else pg_insert
    indices = ["thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"]
    with db.session() as session:
        db.lock_writes(session)
        for write in writes:
            statement = factory(CheckpointWriteRow).values(**key.model_dump(), **write.model_dump())
            statement = (
                statement.on_conflict_do_update(
                    index_elements=indices,
                    set_={
                        "channel": statement.excluded.channel,
                        "value": statement.excluded.value,
                        "task_path": statement.excluded.task_path,
                    },
                )
                if write.idx < 0
                else statement.on_conflict_do_nothing(index_elements=indices)
            )
            session.execute(statement)
        session.commit()


def _view(session: Session, row: CheckpointRow) -> CheckpointRecord:
    key = CheckpointKey(
        thread_id=row.thread_id,
        checkpoint_ns=row.checkpoint_ns,
        checkpoint_id=row.checkpoint_id,
    )
    writes = session.scalars(
        select(CheckpointWriteRow)
        .filter_by(**key.model_dump())
        .order_by(CheckpointWriteRow.task_path, CheckpointWriteRow.task_id, CheckpointWriteRow.idx)
    )
    return CheckpointRecord(
        key=key,
        checkpoint=row.checkpoint,
        metadata=row.metadata_bytes,
        parent_checkpoint_id=row.parent_checkpoint_id,
        writes=[
            CheckpointWrite(
                task_id=write.task_id,
                idx=write.idx,
                channel=write.channel,
                value=write.value,
                task_path=write.task_path,
            )
            for write in writes
        ],
    )


def list_checkpoints(db: Database, query: CheckpointQuery) -> list[CheckpointRecord]:
    """Return snapshots newest first with stable ordering within each checkpoint."""
    statement = select(CheckpointRow).order_by(
        CheckpointRow.checkpoint_id.desc(), CheckpointRow.thread_id, CheckpointRow.checkpoint_ns
    )
    for name in ("thread_id", "checkpoint_ns", "checkpoint_id"):
        if (value := getattr(query, name)) is not None:
            statement = statement.filter_by(**{name: value})
    if query.before is not None:
        statement = statement.where(CheckpointRow.checkpoint_id < query.before)
    if query.limit is not None:
        statement = statement.limit(query.limit)
    with db.session() as session:
        return [_view(session, row) for row in session.scalars(statement)]


def delete_thread(db: Database, thread_id: str) -> None:
    """Delete only disposable graph snapshots, preserving all authoritative audit tables."""
    with db.session() as session:
        db.lock_writes(session)
        session.execute(delete(CheckpointWriteRow).where(CheckpointWriteRow.thread_id == thread_id))
        session.execute(delete(CheckpointRow).where(CheckpointRow.thread_id == thread_id))
        session.commit()
