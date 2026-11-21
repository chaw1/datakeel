# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify precise session telemetry without increasing the call-tree query budget."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import event

from datakeel.core.agent_models import Conversation, ConversationCreate
from datakeel.core.harness_models import ModelCallTrace, TokenUsage
from datakeel.delegation.models import CallTree, CallTreeNode
from datakeel.delegation.tree import call_tree
from datakeel.storage import conversation_store
from datakeel.storage.harness_rows import ModelCallTraceRow
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
    db: Database, identifier: str, parent: Conversation | None = None
) -> Conversation:
    return conversation_store.store(
        db,
        Conversation(
            id=identifier,
            config=ConversationCreate(),
            created_at=_START,
            parent_conversation_id=parent.id if parent else None,
            root_conversation_id=parent.id if parent else None,
            agent_name=identifier,
            agent_path=f"{parent.agent_path}/{identifier}" if parent else "main",
            depth=1 if parent else 0,
        ),
    )


def _trace(
    db: Database, conversation: Conversation, ordinal: int, provider: str, model: str
) -> ModelCallTrace:
    trace = ModelCallTrace(
        id=f"trace-{ordinal}",
        reservation_id=f"reservation-{ordinal}",
        conversation_id=conversation.id,
        accounting_conversation_id=conversation.root_conversation_id or conversation.id,
        agent_path=conversation.agent_path,
        depth=conversation.depth,
        turn=ordinal + 1,
        model=model,
        provider=provider,
        segments=[],
        usage=TokenUsage(output_tokens=ordinal + 1),
        accounted_tokens=(ordinal + 1) * 10,
        latency_ms=1,
        stop_reason="stop",
        tool_calls=7,
        cost_usd=Decimal("0.000000111") * (ordinal + 1),
        price_version="fixture",
        created_at=_START + timedelta(seconds=ordinal),
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
                cost_nanos=int(trace.cost_usd * 1_000_000_000),
                payload=trace.model_dump(mode="json"),
                created_at=trace.created_at.timestamp(),
            )
        )
        session.commit()
    return trace


def _tools(db: Database, conversation: Conversation, spans: list[tuple[str, float]]) -> None:
    with db.session() as session:
        for ordinal, (status, elapsed_ms) in enumerate(spans):
            session.add(
                ToolInvocationRow(
                    id=f"{conversation.id}-tool-{ordinal}",
                    name=f"tool-{ordinal}",
                    actor="local",
                    session_id=conversation.id,
                    parameters_summary={"digest": "fixture", "keys": []},
                    status=status,
                    elapsed_ms=elapsed_ms,
                    started_at=_START.timestamp() + ordinal,
                )
            )
        session.commit()


def test_call_tree_aggregates_precise_telemetry_in_four_queries(db: Database) -> None:
    """Charge all parent and specialist calls once while retaining first-seen model order."""
    root = _conversation(db, "root")
    child = _conversation(db, "analyst", root)
    idle = _conversation(db, "idle", root)
    traces = [
        _trace(db, root, 0, "fake", "alpha"),
        _trace(db, child, 1, "other", "beta"),
        _trace(db, root, 2, "fake", "alpha"),
        _trace(db, child, 3, "other", "alpha"),
    ]
    _tools(db, root, [("RUNNING", 1.234), ("FAILED", 2.0)])
    _tools(db, child, [("SUCCEEDED", 3.234)])
    with _statements(db) as statements:
        tree = call_tree(db, child.id)
    assert len(statements) == 4
    assert tree.traces == traces
    assert tree.total_tokens == 100
    assert tree.total_cost_usd == Decimal("0.000001110")
    assert tree.total_tool_calls == 3
    assert tree.total_tool_elapsed_ms == 6.47
    assert tree.models == ["fake/alpha", "other/beta", "other/alpha"]
    assert [node.id for node in tree.nodes] == [root.id, child.id, idle.id]
    assert [
        (
            node.tokens,
            node.cost_usd,
            node.model_calls,
            node.tool_elapsed_ms,
            node.failed_tools,
            node.tools,
        )
        for node in tree.nodes
    ] == [
        (40, Decimal("0.000000444"), 2, 3.23, 1, ["tool-0", "tool-1"]),
        (60, Decimal("0.000000666"), 2, 3.23, 0, ["tool-0"]),
        (0, Decimal(0), 0, 0.0, 0, []),
    ]


def test_call_tree_defaults_preserve_legacy_payloads_and_idle_sessions(db: Database) -> None:
    """Old payloads and sessions without recorded activity expose zero-valued telemetry."""
    root = _conversation(db, "root")
    node = CallTreeNode(
        id=root.id,
        parent_id=None,
        root_id=root.id,
        agent_name=root.agent_name,
        agent_path=root.agent_path,
        depth=0,
        parent_tool_call_id=None,
        tokens=0,
        tools=[],
    )
    legacy = CallTree(nodes=[node], traces=[])
    with _statements(db) as statements:
        assert call_tree(db, root.id) == legacy
    assert len(statements) == 4
    assert (node.cost_usd, node.model_calls, node.tool_elapsed_ms, node.failed_tools) == (
        0,
        0,
        0,
        0,
    )
    assert (
        legacy.total_tokens,
        legacy.total_cost_usd,
        legacy.total_tool_calls,
        legacy.total_tool_elapsed_ms,
        legacy.models,
    ) == (0, 0, 0, 0, [])
