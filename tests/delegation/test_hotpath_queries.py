# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound delegation reads while preserving hierarchy, ownership and dispatch ordering."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from datakeel.core.agent_models import Conversation, ConversationCreate, ToolCall
from datakeel.core.harness_models import ModelCallTrace, TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import get_agent
from datakeel.delegation.models import ChildResult
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_rows import ConversationRow
from datakeel.storage.harness_rows import ModelCallTraceRow
from datakeel.storage.identity_sessions import bind_session_actor, session_actor
from datakeel.storage.tool_rows import ToolInvocationRow

if TYPE_CHECKING:
    from collections.abc import Generator

    from datakeel.storage.database import Database

_START = datetime(2026, 1, 1, tzinfo=UTC)


@contextmanager
def _statements(db: Database) -> Generator[list[str]]:
    recorded: list[str] = []

    def record(_connection: object, _cursor: object, sql: str, *_args: object) -> None:
        recorded.append(sql)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(db.engine, "before_cursor_execute", record)


def _conversation(
    identifier: str, ordinal: int = 0, parent: Conversation | None = None
) -> Conversation:
    return Conversation(
        id=identifier,
        config=ConversationCreate(),
        created_at=_START + timedelta(seconds=ordinal),
        parent_conversation_id=parent.id if parent else None,
        root_conversation_id=(parent.root_conversation_id or parent.id) if parent else None,
        agent_name="catalog-analyst" if parent else "main",
        agent_path=f"{parent.agent_path}/catalog-analyst#{ordinal}" if parent else "main",
        depth=parent.depth + 1 if parent else 0,
        parent_tool_call_id=f"call-{identifier}" if parent else None,
    )


def _unrelated(db: Database, size: int) -> None:
    for index in range(size):
        root = memory.store(db, _conversation(f"unrelated-{index}"))
        memory.store(db, _conversation(f"unrelated-child-{index}", 1, root))


def test_list_all_skips_child_validation_and_keeps_root_creation_order(db: Database) -> None:
    """Malformed hidden children cannot break root lists, but explicit child reads validate."""
    later = memory.store(db, _conversation("later", 2))
    earlier = memory.store(db, _conversation("earlier", 1))
    with db.session() as session:
        session.add(ConversationRow(id="child", payload={"parent_conversation_id": earlier.id}))
        session.commit()
    with _statements(db) as sql:
        assert memory.list_all(db) == [earlier, later]
    assert len(sql) == 1
    with pytest.raises(ValidationError, match="config"):
        memory.list_all(db, include_children=True)


def test_child_count_inspects_only_parent_and_agent_payload_fields(db: Database) -> None:
    """Count children with no transcript validation and no cross-parent/name matches."""
    pairs = [
        ("parent", "analyst"),
        ("parent", "analyst"),
        ("other", "analyst"),
        ("parent", "other"),
    ]
    with db.session() as session:
        for index, (parent, agent) in enumerate(pairs):
            session.add(
                ConversationRow(
                    id=str(index), payload={"parent_conversation_id": parent, "agent_name": agent}
                )
            )
        session.add(ConversationRow(id="legacy-root", payload={}))
        session.add(
            ConversationRow(id="legacy-child", payload={"parent_conversation_id": "parent"})
        )
        session.commit()
    with _statements(db) as sql:
        assert memory.count_children(db, "parent", "analyst") == 2
    assert len(sql) == 1
    assert memory.count_children(db, "missing", "analyst") == 0
    assert memory.count_children(db, "parent", "main") == 1


def test_family_validates_only_matching_rows_in_creation_order(db: Database) -> None:
    """Root IDs and descendant root references retain one ordered family, ignoring other rows."""
    root = memory.store(db, _conversation("root"))
    child = memory.store(db, _conversation("child", 2, root))
    grandchild = memory.store(db, _conversation("grandchild", 1, child))
    with db.session() as session:
        session.add(ConversationRow(id="unrelated", payload={"root_conversation_id": "other"}))
        session.commit()
    with _statements(db) as sql:
        assert memory.list_all(db, root_id=root.id) == [root, grandchild, child]
    assert len(sql) == 1
    assert memory.list_all(db, root_id="missing") == []


def _activity(db: Database, conversation: Conversation, ordinal: int) -> ModelCallTrace:
    trace = ModelCallTrace(
        id=f"trace-{conversation.id}",
        reservation_id=f"reservation-{conversation.id}",
        conversation_id=conversation.id,
        accounting_conversation_id=conversation.root_conversation_id or conversation.id,
        agent_path=conversation.agent_path,
        depth=conversation.depth,
        turn=1,
        model="fake-demo",
        provider="fake",
        segments=[],
        usage=TokenUsage(output_tokens=ordinal + 1),
        latency_ms=1,
        stop_reason="stop",
        tool_calls=3,
        cost_usd=Decimal(0),
        price_version="fixture",
        created_at=_START + timedelta(seconds=ordinal),
        accounted_tokens=ordinal + 1,
    )
    with db.session() as session:
        session.add(
            ModelCallTraceRow(
                id=trace.id,
                reservation_id=trace.reservation_id,
                conversation_id=trace.conversation_id,
                accounting_conversation_id=trace.accounting_conversation_id,
                model=trace.model,
                day="2026-01-01",
                cost_nanos=0,
                payload=trace.model_dump(mode="json"),
                created_at=trace.created_at.timestamp(),
            )
        )
        for offset in (3, 1, 2):
            session.add(
                ToolInvocationRow(
                    id=f"tool-{conversation.id}-{offset}",
                    name=f"tool-{offset}",
                    actor="local",
                    session_id=conversation.id,
                    parameters_summary={"digest": "fixture", "keys": []},
                    started_at=trace.created_at.timestamp() + offset,
                )
            )
        session.commit()
    return trace


@pytest.mark.parametrize(("children", "unrelated"), [(1, 0), (8, 24)])
def test_call_tree_uses_four_queries_and_preserves_tools_traces_and_paths(
    db: Database, children: int, unrelated: int
) -> None:
    """Adding descendants or unrelated history never adds one query per session."""
    root = memory.store(db, _conversation("root"))
    family = [
        root,
        *[memory.store(db, _conversation(f"child-{i}", i, root)) for i in range(children)],
    ]
    traces = [_activity(db, item, i) for i, item in enumerate(reversed(family))]
    _unrelated(db, unrelated)
    with db.session() as session:
        session.add(ConversationRow(id="unrelated-invalid", payload={}))
        session.add(
            ToolInvocationRow(id="unrelated-tool", name="bad", actor="local", parameters_summary={})
        )
        session.commit()
    with _statements(db) as sql:
        tree = call_tree(db, family[-1].id)
    assert len(sql) == 4
    assert tree.traces == traces
    assert [node.id for node in tree.nodes] == [
        item.id for item in sorted(family, key=lambda item: item.agent_path)
    ]
    for node in tree.nodes:
        assert node.root_id == root.id
        assert node.tools == ["tool-1", "tool-2", "tool-3"]
        assert node.tokens == next(
            item.accounted_tokens for item in traces if item.conversation_id == node.id
        )
    tool_sql = next(statement for statement in sql if "FROM tool_invocation" in statement)
    assert "tool_invocation.session_id IN" in tool_sql
    assert "FOR UPDATE" not in tool_sql
    with _statements(db) as root_sql:
        assert call_tree(db, root.id) == tree
    assert len(root_sql) == 4


@pytest.mark.parametrize("unrelated", [0, 24])
def test_delegate_child_creation_has_constant_queries_and_preserves_ordinal_actor_scope(
    db: Database, unrelated: int
) -> None:
    """Count same-agent siblings once while preserving child ownership and capability snapshots."""
    parent = memory.store(db, _conversation("root"))
    bind_session_actor(db, parent.id, "owner")
    for index in (1, 2):
        memory.store(db, _conversation(f"sibling-{index}", index, parent))
    other = _conversation("other-specialist", 3, parent).model_copy(update={"agent_name": "other"})
    memory.store(db, other)
    _unrelated(db, unrelated)
    children: list[Conversation] = []

    def run(child: Conversation, task: str) -> ChildResult:
        assert task == "inspect generated fixtures"
        children.append(child)
        return ChildResult(summary="inspected")

    call = ToolCall(
        name="delegate_agent",
        arguments=JsonDocument({"agent": "catalog-analyst", "task": "inspect generated fixtures"}),
    )
    with _statements(db) as sql:
        result = delegate(db, parent, call, 1, run)
    assert len([statement for statement in sql if statement.startswith("SELECT")]) == 18
    assert len(children) == 1
    child = children[0]
    assert (child.parent_conversation_id, child.root_conversation_id, child.depth) == (
        parent.id,
        parent.id,
        1,
    )
    assert child.agent_path == "main/catalog-analyst#3"
    assert child.parent_tool_call_id == call.id
    assert child.config.max_turns == get_agent("catalog-analyst").max_turns
    assert child.allowed_tools == get_agent("catalog-analyst").tools
    assert session_actor(db, child.id) == "owner"
    assert result.outcome.status == "SUCCEEDED"
    assert result.outcome.content.root == {
        "conversation_id": child.id,
        "summary": "inspected",
        "stop_reason": None,
    }
