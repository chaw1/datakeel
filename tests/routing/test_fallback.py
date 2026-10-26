# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Both model protocols exercise explicit fallback, settlement, and failure boundaries."""

from pathlib import Path
from typing import Literal

import httpx
import pytest
from sqlalchemy import select

from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import MessageInput
from datakeel.harness.service import list_accounts, list_traces
from datakeel.runtime.chat_provider import model_provider
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.database import Database
from tests.routing.protocol_helpers import FailingTransport, ProtocolKind, configure_fallback


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("failure", [429, 500, "timeout"])
def test_transient_protocol_failure_when_backup_configured_settles_each_attempt(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: ProtocolKind,
    failure: int | Literal["timeout"],
) -> None:
    """Every failed attempt must settle before a successful backup may answer."""
    config, settings, backup = configure_fallback(tmp_path, monkeypatch, kind)
    conversation = create_conversation(db, config)
    transport = FailingTransport(kind, failure)
    with (
        httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Summarize the available tables"),
                provider=provider,
            )
        )
    assert any(event.text == "Recovered response." for event in events)
    assert len(transport.models) == 2
    assert transport.models[-1] == backup
    traces = list_traces(db, conversation.id)
    assert len(traces) == 2
    assert traces[0].billing_status == "unknown"
    assert traces[0].accounted_tokens > 0
    assert traces[0].cost_usd > 0
    assert traces[1].model_route is not None
    assert traces[1].model_route.fallback_reason == (
        "timeout" if failure == "timeout" else f"http_{failure}"
    )
    assert traces[1].model_route.attempt == 2
    assert traces[1].model == backup
    assert [trace.turn for trace in traces] == [1, 1]
    stored = get_conversation(db, conversation.id)
    assert stored.turns == 1
    assert stored.events[-1].model_routes == events[-1].model_routes
    assert [route.model for route in stored.events[-1].model_routes] == transport.models
    assert stored.events[-1].model_routes[-1].fallback_reason == (
        "timeout" if failure == "timeout" else f"http_{failure}"
    )
    with db.session() as session:
        statuses = list(session.scalars(select(BudgetReservationRow.status)))
    assert statuses == ["SETTLED", "SETTLED"]
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize("status", [400, 401])
def test_client_protocol_failure_when_backup_configured_does_not_switch(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: ProtocolKind, status: int
) -> None:
    """Bad requests and authentication errors cannot trigger an alternative model attempt."""
    config, settings, _backup = configure_fallback(tmp_path, monkeypatch, kind)
    conversation = create_conversation(db, config)
    transport = FailingTransport(kind, status)
    with (
        httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Inspect available tables"),
                provider=provider,
            )
        )
    assert len(transport.models) == 1
    assert any(event.stop_reason == "provider_error" for event in events)
    assert len(list_traces(db, conversation.id)) == 1
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_all_models_when_transiently_unavailable_stop_after_configured_chain(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: ProtocolKind
) -> None:
    """The last allowed attempt is settled and no framework retry extends the chain."""
    config, settings, _backup = configure_fallback(tmp_path, monkeypatch, kind)
    conversation = create_conversation(db, config)
    transport = FailingTransport(kind, 503, repeat=True)
    with (
        httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        events = list(
            send_message(
                db, conversation.id, MessageInput(content="Inspect collections"), provider=provider
            )
        )
    assert len(transport.models) == 2
    assert any(event.stop_reason == "provider_error" for event in events)
    assert len(list_traces(db, conversation.id)) == 2
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))
