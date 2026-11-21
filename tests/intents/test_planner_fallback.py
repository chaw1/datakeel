# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Planner retries preserve independent accounting and public route visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.agent.service import create_conversation
from datakeel.core.agent_models import ConversationCreate, ModelRequest, ModelResponse
from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.routing_models import ModelRouteDecision
from datakeel.harness.service import list_accounts, list_traces
from datakeel.intents.model_parse import AGENT_NAME
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.service import model_decisions
from datakeel.storage.budget_rows import BudgetReservationRow
from tests.intents.model_support import PlannerProvider, send_planner
from tests.routing.protocol_helpers import configure_fallback

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("status", [None, 429, 500, 503, 400, 401])
def test_planner_failure_falls_back_only_when_retryable_and_settles_every_attempt(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int | None
) -> None:
    """Retries use priced backups; bad input or credentials stop after one settled call."""
    config, _settings, backup = configure_fallback(tmp_path, monkeypatch, "openai")
    conversation = create_conversation(db, config)
    reason = "timeout" if status is None else f"http_{status}"
    failure = ProviderError(reason, status_code=status)
    provider = PlannerProvider(failures={1: failure})
    events = send_planner(db, conversation.id, provider)
    count = 2 if failure.retryable else 1
    assert len(provider.requests) == count
    intent = next(event.intent for event in events if event.intent is not None)
    assert intent.kind == ("plan" if failure.retryable else "failed")
    traces = list_traces(db, conversation.id)
    assert len(traces) == count
    assert len({trace.reservation_id for trace in traces}) == count
    assert all(trace.agent_path == AGENT_NAME for trace in traces)
    assert traces[0].billing_status == "unknown"
    assert traces[0].accounted_tokens > 0
    routes = events[-1].model_routes
    assert routes == [trace.model_route for trace in traces]
    assert [route.attempt for route in routes] == list(range(1, count + 1))
    assert all(route.tier == "simple" for route in routes)
    if failure.retryable:
        assert traces[1].billing_status == "actual"
        assert routes[1].model == provider.requests[1].model == backup
        assert routes[1].fallback_reason == reason
    with db.session() as session:
        assert list(session.scalars(select(BudgetReservationRow.status))) == ["SETTLED"] * count
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))


def test_planner_done_routes_exclude_workflow_classifier_attempt(db: Database) -> None:
    """A workflow classifier and a planner can share one response without leaking routes."""
    conversation = create_conversation(db, ConversationCreate())
    provider = PlannerProvider(['{"kind":"none"}'])
    events = send_planner(db, conversation.id, provider, text="run")
    traces = list_traces(db, conversation.id)
    assert [trace.agent_path for trace in traces] == ["main", AGENT_NAME]
    assert all(trace.call_type == "intent_classifier" for trace in traces)
    assert events[-1].model_routes == [traces[1].model_route]
    assert len(events[-1].model_routes) == 1


def test_planner_done_routes_only_include_current_response(db: Database) -> None:
    """Planner-only turns must advance the response window so old attempts stay hidden."""
    conversation = create_conversation(db, ConversationCreate())
    for _ in range(2):
        events = send_planner(db, conversation.id, PlannerProvider())
        assert len(events[-1].model_routes) == 1
    assert [trace.turn for trace in list_traces(db, conversation.id)] == [1, 2]
    rules = PlannerProvider()
    events = send_planner(db, conversation.id, rules, text="建红绿灯框标注, 两人交叉、抽 10%")
    assert rules.requests == []
    assert events[-1].model_routes == []


def test_main_classifier_with_route_metadata_is_still_excluded(db: Database) -> None:
    """Non-null route metadata cannot make an unrelated classifier look like a planner."""
    conversation = create_conversation(db, ConversationCreate())
    events = send_planner(db, conversation.id, PlannerProvider())
    account = ModelAccount(
        db,
        CallContext(
            conversation_id=conversation.id,
            turn=1,
            provider="fake",
            limits=BudgetLimits(),
            call_type="intent_classifier",
        ),
    )
    request = ModelRequest(model="fake-demo", messages=[], tools=[], segments=[])
    route = ModelRouteDecision(tier="high_risk", model="fake-demo", pinned=True)
    account.complete(request, lambda _request: ModelResponse(), route)
    traces = list_traces(db, conversation.id)
    assert len(traces) == 2
    assert all(trace.model_route is not None for trace in traces)
    assert model_decisions(db, conversation.id, 0) == events[-1].model_routes
    assert len(model_decisions(db, conversation.id, 0)) == 1
