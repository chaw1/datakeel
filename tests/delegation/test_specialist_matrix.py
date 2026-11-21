# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Discovered domain specialists retain their read scopes and ancestor secret boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ConversationCreate, MessageInput, ScriptedResponse, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import get_agent
from datakeel.delegation.tree import call_tree
from datakeel.harness.training_cases import seed_training_case
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage import conversation_store
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.conversation_secrets import get_canary
from tests.delegation.test_execution import request, search
from tests.kg.helpers import graph_product, seed_graph
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

SPECIALISTS = (
    "catalog-analyst",
    "evidence-reviewer",
    "kg-standard-analyst",
    "metric-manager",
    "production-ops",
    "training-auditor",
)
DOMAIN_SPECIALISTS = ("production-ops", "training-auditor", "kg-standard-analyst")
FORBIDDEN_TOOLS = ("list_metrics", "update_metric")


@pytest.mark.parametrize("query", ["delegate_agent", "training-auditor", "production-ops"])
def test_discovery_advertises_compact_registered_specialists(db: Database, query: str) -> None:
    """Both the delegation name and specialist domain terms discover its complete registry."""
    root = create_conversation(db, ConversationCreate())
    catalog = ToolCatalog(conversation_store.get(db, root.id))
    outcome = catalog.invoke(
        db,
        ToolCall(name="tool_search", arguments=JsonDocument({"query": query})),
        ToolCallContext(session_id=root.id),
    )
    assert outcome.status == "SUCCEEDED"
    description = catalog.loaded["delegate_agent"].description
    assert tuple(description.partition(":")[2].strip().removesuffix(".").split(", ")) == SPECIALISTS
    assert len(description) <= 180
    assert "\n" not in description


def _allowed_read(db: Database, directory: Path, specialist: str) -> ToolCall:
    if specialist == "production-ops":
        project, _ = production_fixture(db)
        return ToolCall(name="project_progress", arguments=JsonDocument({"project_id": project.id}))
    if specialist == "training-auditor":
        fixture = seed_training_case(db, directory)
        return ToolCall(
            name="training_distribution", arguments=JsonDocument({"dataset_id": fixture.dataset_id})
        )
    product, source = graph_product()
    seed_graph(db, product, source)
    return ToolCall(name="query_kg", arguments=JsonDocument({"name": "Acme"}))


@pytest.mark.parametrize("specialist", DOMAIN_SPECIALISTS)
def test_delegated_domain_reads_succeed_and_out_of_scope_calls_are_audited(
    db: Database, tmp_path: Path, specialist: str
) -> None:
    """Real child graphs execute an allowed read and reject both read and write scope escapes."""
    allowed = _allowed_read(db, tmp_path, specialist)
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [
            search(),
            request(name=specialist),
            ScriptedResponse(
                agent=specialist,
                tool_calls=[
                    ToolCall(name="tool_search", arguments=JsonDocument({"query": name}))
                    for name in (allowed.name, *FORBIDDEN_TOOLS)
                ],
            ),
            ScriptedResponse(
                agent=specialist,
                tool_calls=[allowed, *[ToolCall(name=name) for name in FORBIDDEN_TOOLS]],
            ),
            ScriptedResponse(agent=specialist, content="Scoped domain review complete."),
            ScriptedResponse(agent="main", content="Domain review received."),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="Inspect domain"), provider=fake))
    child = conversation_store.get(db, call_tree(db, root.id).nodes[1].id)
    outcomes = {event.outcome.name: event.outcome for event in events if event.outcome}
    assert outcomes[allowed.name].status == "SUCCEEDED", outcomes[allowed.name].error
    assert outcomes[allowed.name].content.root["data"]
    assert outcomes["delegate_agent"].status == "SUCCEEDED"
    assert child.allowed_tools == get_agent(specialist).tools
    assert {tool.name for tool in fake.requests[3].tools} <= {
        *get_agent(specialist).tools,
        "tool_search",
    }
    assert allowed.name in {tool.name for tool in fake.requests[3].tools}
    for name in FORBIDDEN_TOOLS:
        assert outcomes[name].status == "FAILED"
        assert outcomes[name].error == "Tool outside delegated scope"
    assert [(audit.kind, audit.reason) for audit in list_audit(db, child.id)] == [
        ("DELEGATION_DENIED", "tool_scope_exceeded"),
        ("DELEGATION_DENIED", "tool_scope_exceeded"),
    ]
    assert fake.script_errors == []
    assert fake.script == []


@pytest.mark.parametrize("specialist", DOMAIN_SPECIALISTS)
def test_domain_specialists_block_ancestor_canaries_before_persistence(
    db: Database, specialist: str
) -> None:
    """Each new specialist stops a parent secret at the child boundary and never resumes root."""
    root = create_conversation(db, ConversationCreate())
    canary = get_canary(db, root.id)
    fake = FakeProvider(
        [
            search(),
            request(name=specialist),
            ScriptedResponse(agent=specialist, content=canary),
            ScriptedResponse(agent="main", content="must not run"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="Inspect domain"), provider=fake))
    nodes = call_tree(db, root.id).nodes
    assert len(nodes) == 2
    assert any(
        event.stop_reason == "canary_leak" and event.agent_path == "main" for event in events
    )
    assert not any(event.event == "text" for event in events)
    assert len(fake.script) == 1
    assert list_audit(db, root.id)[0].kind == "CANARY_LEAK"
    for node in nodes:
        assert canary not in conversation_store.get(db, node.id).model_dump_json()
        for checkpoint in list_checkpoints(db, CheckpointQuery(thread_id=node.id)):
            assert canary.encode() not in checkpoint.checkpoint + checkpoint.metadata
