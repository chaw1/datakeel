# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question threads persist, isolate users and erase replayable turns independently."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from datakeel.ask import service
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.models import AssetRef, utcnow
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_conversation_rows import AskConversationRow
from datakeel.storage.ask_conversations import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    store_conversation_turn,
)
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database
from tests.assets.entry_helpers import grant, publish, revoke

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def test_threads_restore_after_engine_restart_and_do_not_cross(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Independent thread IDs survive replacement of every connection pool handle."""
    first = ask_data(db, AskRequest(question="上个季度华东零售额", reference_instant=REFERENCE))
    second = ask_data(db, AskRequest(question="去年华北订单数", reference_instant=REFERENCE))
    assert first.conversation_id
    assert second.conversation_id
    db.engine.dispose()
    db.migrate()
    restored = get_conversation(db, first.conversation_id)
    assert restored.turns == (first,)
    assert restored.current_frame == first.query_frame
    follow = ask_data(
        db,
        AskRequest(
            question="那华南呢", conversation_id=first.conversation_id, reference_instant=REFERENCE
        ),
    )
    assert len(get_conversation(db, first.conversation_id).turns) == 2
    assert get_conversation(db, second.conversation_id).turns == (second,)
    assert follow.query_frame
    assert follow.query_frame.metric_id == "retail_revenue"


def test_delete_removes_thread_frames_answers_and_empty_audit_session(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A deleted turn cannot be replayed through the legacy answer endpoint either."""
    answer = ask_data(db, AskRequest(question="零售额", reference_instant=REFERENCE))
    assert answer.conversation_id
    delete_conversation(db, answer.conversation_id)
    with pytest.raises(NotFoundError):
        get_conversation(db, answer.conversation_id)
    with pytest.raises(NotFoundError):
        get_answer(db, answer.id)
    assert list_conversations(db) == ()
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(AskConversationRow)) == 0
        assert session.scalar(select(func.count()).select_from(AskAnswerRow)) == 0
        assert session.scalar(select(func.count()).select_from(AskSessionRow)) == 0


def test_ownership_checks_apply_to_open_followup_and_delete(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A caller cannot read or continue another actor's query frame using a known ID."""
    conversation = create_conversation(db, actor="alice", title="Revenue")
    assert list_conversations(db, "bob") == ()
    for operation in (get_conversation, delete_conversation):
        with pytest.raises(NotFoundError):
            operation(db, conversation.id, "bob")
    with pytest.raises(NotFoundError):
        ask_data(
            db,
            AskRequest(question="零售额", conversation_id=conversation.id, actor="bob"),
        )
    assert get_conversation(db, conversation.id, "alice").turns == ()


def test_cross_actor_open_never_returns_owned_history(db: Database) -> None:
    """A hidden thread must not become readable when a caller knows its identity."""
    conversation = create_conversation(db, actor="alice", title="Revenue")
    try:
        unauthorized = get_conversation(db, conversation.id, "bob")
    except NotFoundError:
        unauthorized = None
    assert unauthorized is None


def test_retention_removes_expired_replay_but_preserves_recent_threads(
    db: Database, enterprise_sample: EnterpriseSample, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configured retention bound clears the payloads, not just the list entry."""
    old = ask_data(db, AskRequest(question="零售额", reference_instant=REFERENCE))
    recent = create_conversation(db)
    with db.session() as session:
        row = session.get(AskConversationRow, old.conversation_id)
        assert row
        row.updated_at = (utcnow() - timedelta(days=2)).isoformat()
        session.commit()
    monkeypatch.setenv("DATAKEEL_ASK_CONVERSATION_RETENTION_DAYS", "1")
    assert [item.id for item in list_conversations(db)] == [recent.id]
    with pytest.raises(NotFoundError):
        get_answer(db, old.id)


def test_concurrent_update_cannot_overwrite_a_later_turn(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A stale frame reader receives a retryable conflict rather than losing history."""
    first = ask_data(db, AskRequest(question="上个季度零售额", reference_instant=REFERENCE))
    assert first.conversation_id
    stale = get_conversation(db, first.conversation_id)
    ask_data(
        db,
        AskRequest(
            question="那华南呢", conversation_id=first.conversation_id, reference_instant=REFERENCE
        ),
    )
    with pytest.raises(ConflictError, match="changed"):
        store_conversation_turn(
            db,
            AskRequest(question=first.question, reference_instant=REFERENCE),
            first,
            stale,
        )
    assert len(get_conversation(db, first.conversation_id).turns) == 2


def test_followup_rechecks_a_revoked_grant_before_query_execution(
    db: Database, enterprise_sample: EnterpriseSample, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A previously authorized frame is no substitute for the current access policy."""
    asset = publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    grant_id = grant(db, asset, "valid", "query", subject="local-user")
    assert grant_id
    first = ask_data(db, AskRequest(question="上个季度华东零售额", reference_instant=REFERENCE))
    assert first.conversation_id
    revoke(db, grant_id)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A revoked grant must fail before SQL execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    with pytest.raises(AuthorizationError):
        ask_data(
            db,
            AskRequest(
                question="那华南呢",
                conversation_id=first.conversation_id,
                reference_instant=REFERENCE,
            ),
        )
    assert len(get_conversation(db, first.conversation_id).turns) == 1


def test_switching_to_a_protected_metric_needs_its_own_current_grant(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A public source metric cannot confer permission on the follow-up's target metric."""
    first = ask_data(db, AskRequest(question="上个季度订单数", reference_instant=REFERENCE))
    publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    with pytest.raises(AuthorizationError):
        ask_data(
            db,
            AskRequest(
                question="换成零售额",
                conversation_id=first.conversation_id,
                reference_instant=REFERENCE,
            ),
        )
