# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP views, specialist turn limits, reversible actions and old trace schemas compose."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

from datakeel.actions.service import list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.api.app import create_app
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import agents_path
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.memory.service import create_memory
from datakeel.storage import conversation_store as memory
from datakeel.storage.metric_store import get_metric
from tests.asgi_client import TestClient
from tests.delegation.test_execution import request, search

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_demo_and_tree_api_report_measured_nested_steps(db: Database) -> None:
    """The offline public flow discovers a specialist, queries real data and exposes its tree."""
    with TestClient(create_app(db)) as client:
        root = client.post("/api/agent/conversations", json={}).json()
        response = client.post(
            f"/api/agent/conversations/{root['id']}/messages",
            json={"content": "Delegate catalog lineage review."},
        )
        assert response.status_code == 200
        tree = client.get(f"/api/agent/conversations/{root['id']}/tree").json()
        assert len(tree["nodes"]) == 2
        assert tree["nodes"][1]["tools"] == ["list_datasets"]
        assert tree["nodes"][1]["tokens"] > 0
        assert len(client.get("/api/agent/conversations").json()) == 1
        assert len(client.get("/api/agent/conversations/definitions/agents").json()) == 3


def test_child_turn_limit_is_independent_of_parent_turns(db: Database) -> None:
    """Four distinct discovery rounds exhaust only the child's bounded loop."""
    root = create_conversation(db, ConversationCreate())
    child_calls = [
        ModelResponse(
            tool_calls=[ToolCall(name="tool_search", arguments=JsonDocument({"query": name}))]
        )
        for name in ["list_metrics", "explain_metric", "impact_of", "delegate_agent"]
    ]
    fake = FakeProvider([search(), request(), *child_calls, ModelResponse(content="parent")])
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    tree = call_tree(db, root.id)
    assert memory.get(db, tree.nodes[1].id).turns == 4
    assert memory.get(db, root.id).turns == 3
    assert any(event.outcome and event.outcome.error == "max_turns" for event in events)
    assert events[-1].event == "done"


def test_child_memory_use_reaches_root_terminal_event(db: Database) -> None:
    """A memory relevant only to a child remains visible in both child and parent usage notices."""
    entry = create_memory(db, MemoryCreate(content="child task catalog observations"))
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [search(), request(), ModelResponse(content="child"), ModelResponse(content="parent")]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    child_done = next(
        event for event in events if event.event == "done" and event.agent_path != "main"
    )
    assert child_done.used_memory_ids == [entry.id]
    assert events[-1].used_memory_ids == [entry.id]


def test_metric_specialist_reversible_action_executes_without_nested_pause(
    db: Database,
    tmp_path: Path,
) -> None:
    """A permitted metric update reuses the normal automatic reversible execution policy."""
    fixture = seed_enterprise_case(db, tmp_path)
    metric = get_metric(db, "retail_revenue")
    definition = metric.definition.model_copy(
        update={"description": "Revised generated definition"}
    )
    root = create_conversation(db, ConversationCreate(dataset_id=fixture.dataset_id))
    fake = FakeProvider(
        [
            search(),
            request(name="metric-manager"),
            ModelResponse(
                tool_calls=[
                    ToolCall(name="tool_search", arguments=JsonDocument({"query": "update_metric"}))
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        name="update_metric",
                        arguments=JsonDocument.model_validate(
                            {"definition": definition.model_dump(mode="json")}
                        ),
                    )
                ]
            ),
            ModelResponse(content="metric updated"),
            ModelResponse(content="parent"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    assert len(list_runs(db)) == 1
    assert list_runs(db)[0].status == "SUCCEEDED"
    assert not any(event.stop_reason == "approval_required" for event in events)


def test_invalid_delegation_arguments_and_unknown_names_are_cached_failures(db: Database) -> None:
    """Validation errors remain ordinary inspectable tool outcomes without starting children."""
    root = memory.create(db, ConversationCreate())
    for arguments in [{}, {"agent": "missing", "task": "inspect"}]:
        call = ToolCall(name="delegate_agent", arguments=JsonDocument(arguments))
        result = delegate(
            db, root, call, 1, lambda _child, _task: (_ for _ in ()).throw(AssertionError())
        )
        assert result.outcome.status == "FAILED"
        assert result.outcome.error
    assert len(call_tree(db, root.id).nodes) == 1


def test_agent_contract_locator_uses_installed_wheel_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed modules resolve bundled contracts when a checkout contracts path is absent."""
    monkeypatch.setattr(
        "datakeel.delegation.loader.__file__", str(tmp_path / "datakeel/delegation/loader.py")
    )
    assert agents_path() == tmp_path / "datakeel/_contracts/agents"


def test_old_trace_table_receives_nullable_parent_columns(unmigrated_db: Database) -> None:
    """Upgrade both supported databases without rewriting historical trace payloads."""
    with unmigrated_db.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE model_call_trace (id VARCHAR PRIMARY KEY, "
                "reservation_id VARCHAR NOT NULL UNIQUE, conversation_id VARCHAR NOT NULL, "
                "model VARCHAR NOT NULL, day VARCHAR NOT NULL, cost_nanos BIGINT NOT NULL, "
                "payload JSON NOT NULL, created_at FLOAT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_call_trace VALUES "
                "('old','reservation','root','fake-script','2026-01-01',0,'{}',0)"
            )
        )
    unmigrated_db.migrate()
    unmigrated_db.migrate()
    columns = {
        column["name"]: column
        for column in inspect(unmigrated_db.engine).get_columns("model_call_trace")
    }
    for name in ["accounting_conversation_id", "agent_path", "depth", "parent_tool_call_id"]:
        assert columns[name]["nullable"]
    with unmigrated_db.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT conversation_id FROM model_call_trace WHERE id='old'"))
            == "root"
        )
