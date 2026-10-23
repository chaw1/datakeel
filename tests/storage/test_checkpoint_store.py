# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Opaque checkpoint rows share migrations and never own authoritative audit state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import LargeBinary, inspect, select

from datakeel.core.agent_models import ConversationCreate, MessageInput
from datakeel.storage import checkpoint_store as store
from datakeel.storage import conversation_store
from datakeel.storage.budget_rows import BudgetAccountRow
from datakeel.storage.harness_rows import ModelCallTraceRow

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session

    from datakeel.storage.database import Database


def test_binary_storage_when_payload_contains_nul_round_trips_on_both_dialects(
    db: Database,
) -> None:
    """Raw binary payloads never pass through PostgreSQL JSON string validation."""
    key = store.CheckpointKey(thread_id="thread", checkpoint_id="001")
    record = store.CheckpointRecord(key=key, checkpoint=b"\x00snapshot\xff", metadata=b"\x00meta")
    store.put_checkpoint(db, record)
    store.put_writes(
        db,
        key,
        [
            store.CheckpointWrite(
                task_id="task",
                idx=0,
                channel="binary",
                value=b"\x00write\xff",
            )
        ],
    )
    actual = store.list_checkpoints(db, store.CheckpointQuery(limit=1))
    assert len(actual) == 1
    assert actual[0].checkpoint == record.checkpoint
    assert actual[0].metadata == record.metadata
    assert actual[0].writes[0].value == b"\x00write\xff"
    assert store.list_checkpoints(db, store.CheckpointQuery(limit=0)) == []
    columns = {
        column["name"]: column["type"] for column in inspect(db.engine).get_columns("checkpoints")
    }
    assert isinstance(columns["checkpoint"], LargeBinary)
    assert isinstance(columns["metadata_bytes"], LargeBinary)


def test_delete_thread_when_audit_exists_preserves_transcript_trace_and_budget(
    db: Database,
) -> None:
    """Checkpoint cleanup cannot remove the audit required to review an earlier response."""
    conversation = conversation_store.create(db, ConversationCreate())
    lease = conversation_store.begin(db, conversation.id, MessageInput(content="Keep this history"))
    conversation_store.finish(db, conversation.id, lease.token, completed=True)
    original = conversation_store.get(db, conversation.id)
    with db.session() as session:
        session.add(BudgetAccountRow(key=conversation.id, token_limit=100, usd_limit_nanos=100))
        session.add(
            ModelCallTraceRow(
                id="trace",
                reservation_id="reservation",
                conversation_id=conversation.id,
                model="fixture",
                day="2026-01-01",
                cost_nanos=0,
                payload={"preserved": True},
            )
        )
        session.commit()
    for thread in (conversation.id, "other"):
        for namespace in ("", "nested"):
            key = store.CheckpointKey(
                thread_id=thread, checkpoint_ns=namespace, checkpoint_id="001"
            )
            store.put_checkpoint(
                db, store.CheckpointRecord(key=key, checkpoint=b"state", metadata=b"meta")
            )
            store.put_writes(
                db, key, [store.CheckpointWrite(task_id="t", idx=0, channel="v", value=b"write")]
            )
    store.delete_thread(db, conversation.id)
    assert conversation_store.get(db, conversation.id) == original
    assert [row.key.thread_id for row in store.list_checkpoints(db, store.CheckpointQuery())] == [
        "other",
        "other",
    ]
    with db.session() as session:
        assert session.get(BudgetAccountRow, conversation.id) is not None
        assert session.get(ModelCallTraceRow, "trace").payload == {"preserved": True}
        assert set(session.scalars(select(store.CheckpointWriteRow.thread_id))) == {"other"}


def test_storage_mutations_when_executed_acquire_database_write_lock(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every mutation follows the common SQLite write serialization entry point."""
    calls: list[Session] = []
    original = db.lock_writes

    def tracked(session: Session) -> None:
        calls.append(session)
        original(session)

    monkeypatch.setattr(db, "lock_writes", tracked)
    key = store.CheckpointKey(thread_id="thread", checkpoint_id="001")
    store.put_checkpoint(db, store.CheckpointRecord(key=key, checkpoint=b"state", metadata=b"meta"))
    store.put_writes(db, key, [])
    store.delete_thread(db, "thread")
    assert len(calls) == 3
