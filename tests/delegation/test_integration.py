# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP views, specialist turn limits, reversible actions and old trace schemas compose."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text

from datakeel.actions.service import list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.api.app import create_app
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.errors import ValidationError
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.delegation.loader import agents_path
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.memory.service import create_memory
from datakeel.persistence import migrate
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.storage import conversation_store as memory
from datakeel.storage.metric_store import get_metric
from datakeel.storage.migrations import add_nullable_columns
from datakeel.versioning import database_path
from datakeel.versioning.campaign_v2 import status, upgrade
from datakeel.versioning.registry import registry
from tests.asgi_client import TestClient
from tests.delegation.test_execution import request, search

if TYPE_CHECKING:
    from pathlib import Path

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


@pytest.mark.parametrize("missing_columns", [False, True], ids=["baseline", "nullable-helper"])
def test_old_trace_table_receives_nullable_parent_columns(
    unmigrated_db: Database, *, missing_columns: bool
) -> None:
    """Separate SQLite's nullable helper contract from strict admission and PG W3 migration."""
    db = unmigrated_db
    db.migrate(schema_contributions(), canonical=canonical_schema())
    assert len(inspect(db.engine).get_table_names()) == 102
    assert "datakeel_schema_versions" not in inspect(db.engine).get_table_names()
    if db.sqlite:
        assert status(database_path(db), get_settings().home, registry()).state == "unversioned"
    else:
        with db.engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")).startswith("test_")
    added = ("accounting_conversation_id", "agent_path", "depth", "parent_tool_call_id")
    historical = text(
        "SELECT id, reservation_id, conversation_id, model, day, cost_nanos, payload, "
        "created_at FROM model_call_trace WHERE id='old'"
    )
    with db.engine.begin() as connection:
        if missing_columns:
            for name in added:
                connection.execute(text(f"ALTER TABLE model_call_trace DROP COLUMN {name}"))
        connection.execute(
            text(
                "INSERT INTO model_call_trace "
                "(id, reservation_id, conversation_id, model, day, cost_nanos, payload, "
                "created_at) VALUES "
                "('old','reservation','root','fake-script','2026-01-01',7,:payload,0)"
            ),
            {"payload": '{"historical":["trace",null,7],"nested":{"retained":true}}'},
        )
        before = connection.execute(historical).one()
    present = {column["name"] for column in inspect(db.engine).get_columns("model_call_trace")}
    assert set(added) & present == (set() if missing_columns else set(added))
    if db.sqlite:
        _prepare_sqlite_trace(db, missing_columns=missing_columns)
    for _ in range(2):
        if db.sqlite and missing_columns:
            with pytest.raises(ValidationError, match="Database invalid"):
                migrate(db)
        else:
            migrate(db)
        columns = {
            column["name"]: column for column in inspect(db.engine).get_columns("model_call_trace")
        }
        assert all(columns[name]["nullable"] for name in added)
        with db.engine.connect() as connection:
            assert connection.execute(historical).one() == before
            assert connection.execute(
                text(
                    "SELECT accounting_conversation_id, agent_path, depth, parent_tool_call_id "
                    "FROM model_call_trace WHERE id='old'"
                )
            ).one() == (None, None, None, None)
        tables = inspect(db.engine).get_table_names()
        assert len(tables) == (103 if db.sqlite and not missing_columns else 102)
        assert ("datakeel_schema_versions" in tables) == (db.sqlite and not missing_columns)
    if db.sqlite and not missing_columns:
        repeat = upgrade(database_path(db), get_settings(), registry())
        assert (repeat.exit_code, repeat.applied, repeat.backup_manifest) == (0, (), None)


def _prepare_sqlite_trace(db: Database, *, missing_columns: bool) -> None:
    """Keep low-level nullable compatibility outside strict baseline admission."""
    path, settings = database_path(db), get_settings()
    expected = "invalid" if missing_columns else "unversioned"
    assert status(path, settings.home, registry()).state == expected
    with pytest.raises(ValidationError, match=f"Database {expected}"):
        migrate(db)
    if missing_columns:
        # Appended columns differ from frozen DDL; this helper does not admit a legacy shape.
        for _ in range(2):
            with db.engine.begin() as connection:
                add_nullable_columns(connection)
        assert status(path, settings.home, registry()).state == "invalid"
    else:
        result = upgrade(path, settings, registry())
        assert (result.exit_code, result.state, result.applied) == (0, "current", (1, 2))
