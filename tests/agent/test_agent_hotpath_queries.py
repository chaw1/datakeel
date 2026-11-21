# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Batched hydration retains approval history without scanning unrelated action rows."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan, ActionRun
from datakeel.agent import service
from datakeel.agent.memory import conversation_view, conversation_views, workspace
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.agent.recovery import execute_approved
from datakeel.agent.service import list_conversations, resume_conversation, send_message
from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    MessageInput,
    ModelResponse,
    ResumeInput,
)
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.intent_models import ActionChain, ChainStep, IntentResult
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.conversation_store import get, store
from datakeel.storage.identity_sessions import bind_session_actor
from datakeel.storage.intent_chains import save_chain

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy.engine import Connection

    from datakeel.actions.models import PlanStatus, RunStatus
    from datakeel.core.agent_models import Provider
    from datakeel.storage.database import Database

AT = datetime(2026, 1, 1, tzinfo=UTC)


@contextmanager
def _queries(db: Database) -> Iterator[list[str]]:
    statements: list[str] = []

    def record(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        if statement.lstrip().lower().startswith("select"):
            statements.append(" ".join(statement.lower().split()))

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(db.engine, "before_cursor_execute", record)


def _reads(statements: Sequence[str], table: str) -> list[str]:
    return [statement for statement in statements if f"from {table} " in statement + " "]


def _plan(identifier: str) -> ActionPlan:
    return ActionPlan(
        id=identifier,
        action_type="quarantine_files",
        canonical_params={},
        manifest=FrozenManifest(query=ObjectSet(), objects=[], state_digest="state", total_bytes=0),
        plan_digest="plan",
        target_digest="target",
        state_digest="state",
        created_at=AT,
        expires_at=AT + timedelta(hours=1),
        reversible=True,
        external=False,
        impact=ActionImpact(object_count=0, total_bytes=0, external=False),
        actor="local",
        context=ActionContext(),
    )


def _save_plan(db: Database, plan: ActionPlan, status: PlanStatus = "PREPARED") -> None:
    with db.session() as session:
        session.add(
            ActionPlanRow(
                id=plan.id,
                action_type=plan.action_type,
                payload=plan.model_dump(mode="json"),
                status=status,
                created_at=AT.timestamp(),
            )
        )
        session.commit()


def _save_runs(db: Database, plan: ActionPlan, statuses: Sequence[RunStatus]) -> None:
    with db.session() as session:
        for index, status in enumerate(statuses):
            session.add(
                ActionRunRow(
                    id=f"{plan.id}-run-{index}",
                    plan_id=plan.id,
                    action_type=plan.action_type,
                    status=status,
                    created_at=AT.timestamp() + index,
                    error="generated failure" if status == "FAILED" else None,
                )
            )
        session.commit()


def _document(value: AgentEvent) -> JsonDocument:
    return JsonDocument(value.model_dump(mode="json"))


def _chain(identifier: str) -> ActionChain:
    return ActionChain(id=identifier, steps=[ChainStep(id="one", action="quarantine_files")])


def _history(db: Database, identifier: str) -> Conversation:
    plans = [_plan(f"{identifier}-{suffix}") for suffix in ("mixed", "denied", "fallback")]
    for plan, status in zip(plans, ("APPROVED", "REJECTED", "PREPARED"), strict=True):
        _save_plan(db, plan, status)
    _save_runs(db, plans[0], ["SUCCEEDED", "FAILED", "DENIED"])
    _save_runs(db, plans[1], ["DENIED", "DENIED"])
    fallback = ActionRun(
        id=f"{identifier}-historical-run",
        plan_id=plans[2].id,
        action_type=plans[2].action_type,
        status="QUEUED",
        created_at=AT,
    )
    outcomes = [
        ToolOutcome(name="quarantine_files", status="SUCCEEDED", plan=plan) for plan in plans
    ]
    outcomes[2] = outcomes[2].model_copy(update={"run": fallback})
    chain = _chain(f"{identifier}-chain")
    save_chain(db, chain.model_copy(update={"status": "succeeded"}))
    events = [AgentEvent(event="plan", outcome=outcome) for outcome in outcomes]
    events.extend(
        [
            AgentEvent(event="plan", outcome=outcomes[0]),
            AgentEvent(event="intent", intent=IntentResult(kind="plan", text="ready", chain=chain)),
            AgentEvent(
                event="tool_result", outcome=ToolOutcome(name="list_datasets", status="SUCCEEDED")
            ),
            AgentEvent(event="text", text="Original transcript"),
        ]
    )
    return store(
        db,
        Conversation(
            id=identifier,
            config=ConversationCreate(dry_run=True),
            created_at=AT + timedelta(seconds=int(identifier.rsplit("-", 1)[-1])),
            events=[_document(value) for value in events],
            messages=[ChatMessage(role="user", content="Keep my message")],
            turns=3,
        ),
    )


def _unrelated(db: Database, count: int) -> None:
    for index in range(count):
        plan = _plan(f"unrelated-plan-{index}")
        _save_plan(db, plan)
        _save_runs(db, plan, ["SUCCEEDED", "DENIED"])
        conversation = store(
            db,
            Conversation(id=f"other-{index}", config=ConversationCreate(), created_at=AT),
        )
        bind_session_actor(db, conversation.id, "someone-else")


@pytest.mark.parametrize("count", [1, 5])
def test_conversation_views_batch_actions_and_preserve_run_precedence(
    db: Database, count: int
) -> None:
    """One read per action table hydrates multiple histories and chooses the correct attempt."""
    conversations = [_history(db, f"selected-{index}") for index in range(count)]
    _unrelated(db, 12)
    with _queries(db) as queries:
        views = conversation_views(db, conversations)
    assert len(queries) == 3
    for table in ("action_plans", "action_runs", "action_chains"):
        assert len(_reads(queries, table)) == 1
        assert " in (" in _reads(queries, table)[0]
        assert "for update" not in _reads(queries, table)[0]
    assert "order by action_runs.created_at desc" in _reads(queries, "action_runs")[0]
    assert [view.id for view in views] == [item.id for item in conversations]
    for view, original in zip(views, conversations, strict=True):
        outcomes = [value.outcome for value in view.events[:3]]
        assert all(outcome is not None for outcome in outcomes)
        assert [outcome.run.id for outcome in outcomes if outcome and outcome.run] == [
            f"{view.id}-mixed-run-1",
            f"{view.id}-denied-run-1",
            f"{view.id}-historical-run",
        ]
        assert [plan.id for plan in view.pending_plans] == [
            f"{view.id}-mixed",
            f"{view.id}-fallback",
        ]
        assert view.pending_plans[0].status == "APPROVED"
        assert view.events[4].intent is not None
        assert view.events[4].intent.chain is not None
        assert view.events[4].intent.chain.status == "succeeded"
        assert view.messages == original.messages
        assert view.turns == original.turns
        assert view.events[-1].text == "Original transcript"
        assert original.events[0].root["outcome"] != view.events[0].model_dump()["outcome"]


@pytest.mark.parametrize("unrelated", [0, 15])
def test_list_conversations_filters_actors_before_batched_hydration(
    db: Database, unrelated: int
) -> None:
    """Unrelated actors add no SQL queries while legacy unbound roots retain local ownership."""
    legacy = _history(db, "selected-2")
    owned = _history(db, "selected-1")
    bind_session_actor(db, owned.id, "local")
    _unrelated(db, unrelated)
    with _queries(db) as queries:
        views = list_conversations(db, actor="local")
    assert [view.id for view in views] == [owned.id, legacy.id]
    assert len(queries) == 26
    actor_reads = _reads(queries, "identity_sessions")
    assert len(actor_reads) == 2  # One list filter and one authorization projection batch.
    assert all(" in (" in statement for statement in actor_reads)
    for table in ("action_plans", "action_runs", "action_chains"):
        assert len(_reads(queries, table)) == 1
    with _queries(db) as queries:
        assert list_conversations(db, actor="nobody") == []
    assert len(queries) == 2


@pytest.mark.parametrize("unrelated", [0, 15])
def test_workspace_reads_only_referenced_actions_without_resolving_chains(
    db: Database, unrelated: int
) -> None:
    """Workspace ignores even an unavailable chain while preserving plan/run summaries."""
    conversation = _history(db, "selected-0")
    missing_chain = AgentEvent(
        event="intent", intent=IntentResult(kind="plan", text="missing", chain=_chain("missing"))
    )
    conversation = conversation.model_copy(
        update={"events": [*conversation.events, _document(missing_chain)]}
    )
    _unrelated(db, unrelated)
    with _queries(db) as queries:
        result = workspace(db, conversation)
    assert len(queries) == 3
    assert len(_reads(queries, "action_plans")) == 1
    assert len(_reads(queries, "action_runs")) == 1
    assert _reads(queries, "action_chains") == []
    assert "where action_runs.plan_id in (" in _reads(queries, "action_runs")[0]
    assert result.root["dry_run"] is True
    plans = result.root["plans"]
    assert isinstance(plans, list)
    assert [item["plan_id"] for item in plans if isinstance(item, dict)] == [
        "selected-0-mixed",
        "selected-0-denied",
        "selected-0-fallback",
    ]
    assert "selected-0-mixed-run-1" in result.model_dump_json()
    assert "selected-0-mixed-run-2" not in result.model_dump_json()


@pytest.mark.parametrize("unrelated", [0, 15])
@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_execute_approved_reuses_latest_eligible_run_with_one_scoped_read(
    db: Database, unrelated: int, status: RunStatus
) -> None:
    """Recovery skips a newer denial and never fetches unrelated execution history."""
    plan = _plan("recover")
    _save_plan(db, plan, "EXECUTED")
    _save_runs(db, plan, [status, "DENIED"])
    _unrelated(db, unrelated)
    with _queries(db) as queries:
        outcome = execute_approved(db, plan.id)
    assert len(queries) == 2
    run_reads = _reads(queries, "action_runs")
    assert len(run_reads) == 1
    assert "where action_runs.plan_id in (" in run_reads[0]
    assert "order by action_runs.created_at desc" in run_reads[0]
    assert outcome.run is not None
    assert outcome.run.id == "recover-run-0"
    assert outcome.status == ("FAILED" if status == "FAILED" else "SUCCEEDED")
    assert outcome.error == ("generated failure" if status == "FAILED" else None)


@pytest.mark.parametrize(
    "shape", ["same-event", "plan-first", "chain-first", "earlier-conversation"]
)
def test_missing_references_preserve_event_and_conversation_error_order(
    db: Database, shape: str
) -> None:
    """Batch loading raises the same first missing reference as sequential hydration."""
    plan = AgentEvent(
        event="plan",
        outcome=ToolOutcome(name="quarantine_files", status="SUCCEEDED", plan=_plan("absent")),
    )
    chain = AgentEvent(
        event="intent", intent=IntentResult(kind="plan", text="missing", chain=_chain("absent"))
    )
    documents = [_document(plan), _document(chain)]
    if shape == "same-event":
        documents = [_document(plan.model_copy(update={"intent": chain.intent}))]
    elif shape in {"chain-first", "earlier-conversation"}:
        documents.reverse()
    conversations = [Conversation(id="first", config=ConversationCreate(), events=documents)]
    if shape == "earlier-conversation":
        conversations = [
            conversations[0].model_copy(update={"events": documents[:1]}),
            Conversation(id="second", config=ConversationCreate(), events=documents[1:]),
        ]
    message = (
        "Action chain was not found"
        if shape in {"chain-first", "earlier-conversation"}
        else "Action plan not found"
    )
    with pytest.raises(NotFoundError, match=f"^{message}$"):
        conversation_views(db, conversations)
    with pytest.raises(NotFoundError, match=f"^{message}$"):
        conversation_view(db, conversations[0])


def test_empty_conversations_require_no_action_reads(db: Database) -> None:
    """Empty batches and plain text histories do not issue unnecessary action queries."""
    conversation = Conversation(
        id="plain",
        config=ConversationCreate(),
        events=[_document(AgentEvent(event="text", text="hello"))],
    )
    with _queries(db) as queries:
        assert conversation_views(db, []) == []
        view = conversation_view(db, conversation)
    assert queries == []
    assert view.events[0].text == "hello"
    assert view.pending_plans == []


@pytest.mark.parametrize("resume", [False, True])
def test_shared_response_checks_actor_before_claiming_a_lease(
    db: Database, *, resume: bool
) -> None:
    """Both entry points reject another actor before touching durable history or the provider."""
    original = store(db, Conversation(id="owned", config=ConversationCreate()))
    bind_session_actor(db, original.id, "owner")
    provider = FakeProvider([])
    stream = (
        resume_conversation(
            db,
            original.id,
            ResumeInput(plan_id="missing", idempotency_key="foreign-resume"),
            actor="someone-else",
            provider=provider,
        )
        if resume
        else send_message(
            db,
            original.id,
            MessageInput(content="foreign message"),
            actor="someone-else",
            provider=provider,
        )
    )
    with pytest.raises(AuthorizationError, match=r"^Runtime session belongs to another actor$"):
        list(stream)
    assert get(db, original.id) == original
    assert provider.requests == []


def test_closing_response_releases_provider_before_the_conversation_lock(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A disconnected stream closes provider resources before admitting the next response."""
    conversation = store(db, Conversation(id="closing", config=ConversationCreate()))
    provider = FakeProvider([ModelResponse(content="First response")])
    closed: list[str] = []
    original_lock = service.response_lock

    @contextmanager
    def tracking_lock(database: Database, identifier: str) -> Iterator[None]:
        with original_lock(database, identifier):
            try:
                yield
            finally:
                closed.append("lock")

    @contextmanager
    def tracking_provider(
        _config: ConversationCreate, supplied: Provider | None
    ) -> Iterator[Provider]:
        assert supplied is provider
        try:
            yield provider
        finally:
            closed.append("provider")

    monkeypatch.setattr(service, "response_lock", tracking_lock)
    monkeypatch.setattr(service, "provider_session", tracking_provider)
    stream = send_message(db, conversation.id, MessageInput(content="Say hello"), provider=provider)
    assert next(stream).event == "text"
    stream.close()
    assert closed == ["provider", "lock"]
    assert [item.root["event"] for item in get(db, conversation.id).events] == [
        "text",
        "stopped",
        "done",
    ]
