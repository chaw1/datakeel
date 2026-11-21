# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Batch history reads stay scoped, unlocked and faithful to single-record views."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from datakeel.action_store.lifecycle import get_plans_by_ids, get_runs_by_plan_ids, list_runs
from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan
from datakeel.core.agent_models import Conversation, ConversationCreate
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.intent_models import ActionChain, ChainStep
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.action_store import get_plan
from datakeel.storage.conversation_store import store
from datakeel.storage.data_asset_context import read_agent_histories
from datakeel.storage.identity_sessions import (
    IdentitySessionRow,
    bind_session_actor,
    session_actor,
    session_actors,
)
from datakeel.storage.intent_chains import (
    claim_chain,
    get_chain,
    get_chains_by_ids,
    list_chains,
    plan_runs,
    save_chain,
)
from datakeel.storage.intent_rows import ActionChainRow
from datakeel.storage.tool_invocations import list_invocations, list_invocations_by_sessions
from datakeel.storage.tool_rows import ToolInvocationRow

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from sqlalchemy.engine.interfaces import ExecutionContext

    from datakeel.storage.database import Database


@contextmanager
def _statements(db: Database) -> Iterator[list[tuple[str, str]]]:
    statements: list[tuple[str, str]] = []

    def track(*arguments: object) -> None:
        context = cast("ExecutionContext", arguments[4])
        assert context.compiled is not None
        postgres_sql = str(context.compiled.statement.compile(dialect=postgresql.dialect()))
        statements.append((str(arguments[2]), postgres_sql))

    event.listen(db.engine, "before_cursor_execute", track)
    try:
        yield statements
    finally:
        event.remove(db.engine, "before_cursor_execute", track)


def _assert_scoped_read(statements: list[tuple[str, str]], predicate: str) -> None:
    assert len(statements) == 1
    for sql in statements[0]:
        assert sql.startswith("SELECT ")
        assert predicate in sql
        assert "FOR UPDATE" not in sql


def _plan(identifier: str) -> ActionPlanRow:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    plan = ActionPlan(
        id=identifier,
        action_type="delete_files",
        canonical_params={},
        manifest=FrozenManifest(query=ObjectSet(), objects=[], state_digest="fixed", total_bytes=0),
        plan_digest="fixed",
        target_digest="fixed",
        state_digest="fixed",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        reversible=False,
        external=False,
        impact=ActionImpact(object_count=0, total_bytes=0, external=False),
        actor="local",
        context=ActionContext(),
    )
    return ActionPlanRow(
        id=identifier, action_type=plan.action_type, payload=plan.model_dump(mode="json")
    )


@pytest.mark.parametrize(
    "lookup",
    [
        get_plans_by_ids,
        get_runs_by_plan_ids,
        get_chains_by_ids,
        session_actors,
        list_invocations_by_sessions,
    ],
)
def test_empty_batches_issue_no_queries(
    db: Database, lookup: Callable[[Database, Sequence[str]], object]
) -> None:
    """Empty histories never open a database transaction or scan an unrelated table."""
    with _statements(db) as statements:
        assert lookup(db, ()) == {}
    assert statements == []


def test_plan_batch_reads_current_status_and_skips_unrelated_payloads(db: Database) -> None:
    """One unlocked query matches get_plan even when payload status is stale."""
    first, second = _plan("first"), _plan("second")
    first.status, second.status = "APPROVED", "EXECUTED"
    with db.session() as session:
        session.add_all(
            [
                first,
                second,
                ActionPlanRow(id="unrelated", action_type="delete_files", payload={}),
            ]
        )
        session.commit()
    with _statements(db) as statements:
        plans = get_plans_by_ids(db, ("second", "missing", "first", "first"))
    _assert_scoped_read(statements, "WHERE action_plans.id IN (")
    assert plans == {identifier: get_plan(db, identifier) for identifier in ("first", "second")}
    assert [plans[identifier].status for identifier in ("first", "second")] == [
        "APPROVED",
        "EXECUTED",
    ]


def test_run_batch_preserves_newest_first_order_and_denial_details(db: Database) -> None:
    """Interleaved attempts match the full-list subsequences without a full-table scan."""
    with db.session() as session:
        session.add_all([_plan(identifier) for identifier in ("first", "second", "unrelated")])
        session.flush()
        session.add_all(
            [
                ActionRunRow(
                    id=f"run-{index}",
                    plan_id=identifier,
                    action_type="delete_files",
                    status="DENIED" if index % 2 else "SUCCEEDED",
                    created_at=float(index + 1),
                    error="Approval required" if index % 2 else None,
                    completed_at=float(index + 2) if index % 2 == 0 else None,
                )
                for index, identifier in enumerate(
                    ("first", "second", "first", "unrelated", "second")
                )
            ]
        )
        session.commit()
    with _statements(db) as statements:
        runs = get_runs_by_plan_ids(db, ("first", "second", "missing", "first"))
    _assert_scoped_read(statements, "WHERE action_runs.plan_id IN (")
    assert all("ORDER BY action_runs.created_at DESC" in sql for sql in statements[0])
    expected = list_runs(db)
    assert runs == {
        identifier: [run for run in expected if run.plan_id == identifier]
        for identifier in ("first", "second", "missing")
    }
    assert [run.id for run in runs["first"]] == ["run-2", "run-0"]
    assert runs["second"][-1].reason == "Approval required"
    assert plan_runs(db, []) == {}
    assert plan_runs(db, ["first"])["first"] == list(reversed(runs["first"]))


def test_oldest_run_batch_breaks_timestamp_ties_by_id(db: Database) -> None:
    """Chain attempts keep their time/ID order regardless of insertion order."""
    with db.session() as session:
        session.add(_plan("selected"))
        session.flush()
        session.add_all(
            ActionRunRow(
                id=identifier,
                plan_id="selected",
                action_type="delete_files",
                status="SUCCEEDED",
                created_at=created_at,
            )
            for identifier, created_at in (("z", 1.0), ("b", 2.0), ("a", 2.0))
        )
        session.commit()
    with _statements(db) as statements:
        runs = get_runs_by_plan_ids(db, ("selected", "missing"), newest_first=False)
    _assert_scoped_read(statements, "WHERE action_runs.plan_id IN (")
    assert all("ORDER BY action_runs.created_at, action_runs.id" in sql for sql in statements[0])
    assert [run.id for run in runs["selected"]] == ["z", "a", "b"]
    assert runs["missing"] == []
    assert plan_runs(db, ["selected", "missing"]) == runs
    with _statements(db) as statements:
        assert get_runs_by_plan_ids(db, (), newest_first=False) == {}
    assert statements == []


def test_chain_batch_skips_unrelated_payloads_and_omits_missing_ids(db: Database) -> None:
    """Requested chain snapshots preserve every field while unrelated invalid rows stay unread."""
    chains = [
        save_chain(
            db,
            ActionChain(
                id=identifier,
                conversation_id="selected",
                steps=[ChainStep(id="1", action="delete_files")],
            ),
        )
        for identifier in ("first", "second")
    ]
    with db.session() as session:
        session.add(ActionChainRow(id="unrelated", actor="local", updated_at=0, payload={}))
        session.commit()
    with _statements(db) as statements:
        found = get_chains_by_ids(db, ("second", "missing", "first", "first"))
    _assert_scoped_read(statements, "WHERE action_chains.id IN (")
    assert found == {chain.id: get_chain(db, chain.id) for chain in chains}
    assert list_chains(db, "selected") == chains
    assert claim_chain(db, chains[0].id, "local") == chains[0]
    assert get_chains_by_ids(db, [chains[0].id])[chains[0].id] == chains[0]
    with pytest.raises(ConflictError, match=r"^This chain is already being run$"):
        claim_chain(db, chains[0].id, "local")
    with pytest.raises(AuthorizationError, match="only be run by the person"):
        get_chain(db, chains[0].id, actor="other")
    with pytest.raises(NotFoundError, match=r"^Action chain was not found$"):
        get_chain(db, "missing")


def test_actor_batch_matches_legacy_defaults_and_bound_owners(db: Database) -> None:
    """Absent rows retain local access while bound actors, including empty names, stay exact."""
    with db.session() as session:
        session.add_all(
            [
                IdentitySessionRow(session_id="first", actor="person-a"),
                IdentitySessionRow(session_id="second", actor=""),
                IdentitySessionRow(session_id="unrelated", actor="person-b"),
            ]
        )
        session.commit()
    identifiers = ("first", "second", "missing", "first")
    with _statements(db) as statements:
        actors = session_actors(db, identifiers)
    _assert_scoped_read(statements, "WHERE identity_sessions.session_id IN (")
    assert actors == {identifier: session_actor(db, identifier) for identifier in identifiers}
    assert actors["missing"] == "local"


def test_invocation_batch_preserves_dispatch_order_and_excludes_unbound(db: Database) -> None:
    """Mixed session histories retain their exact ordering and empty requested sessions."""
    with db.session() as session:
        session.add_all(
            [
                ToolInvocationRow(
                    id=f"invocation-{index}",
                    name="tool_search",
                    actor="local",
                    session_id=identifier,
                    parameters_summary={"digest": "fixed", "keys": []},
                    started_at=float(index + 1),
                )
                for index, identifier in enumerate(("second", "first", None, "second", "unrelated"))
            ]
        )
        session.commit()
    with _statements(db) as statements:
        found = list_invocations_by_sessions(db, ("first", "second", "missing", "first"))
    _assert_scoped_read(statements, "WHERE tool_invocation.session_id IN (")
    assert all("ORDER BY tool_invocation.started_at" in sql for sql in statements[0])
    assert found == {
        identifier: list_invocations(db, identifier)
        for identifier in ("first", "second", "missing")
    }
    assert [invocation.id for invocation in found["second"]] == ["invocation-0", "invocation-3"]


@pytest.mark.parametrize("count", [0, 1, 6])
def test_history_authorization_batches_owners_for_all_selected_conversations(
    db: Database, count: int
) -> None:
    """Current grants still gate each history while owner reads stay constant for selected roots."""
    conversations = [
        store(db, Conversation(id=f"history-{index}", config=ConversationCreate()))
        for index in range(count)
    ]
    for index, conversation in enumerate(conversations):
        if index % 2:
            bind_session_actor(db, conversation.id, f"actor-{index}")
    with _statements(db) as statements:
        assert read_agent_histories(db, conversations) == conversations
    identity_reads = [pair for pair in statements if "FROM identity_sessions" in pair[0]]
    if count:
        _assert_scoped_read(identity_reads, "WHERE identity_sessions.session_id IN (")
    else:
        assert statements == []
