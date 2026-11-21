# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native Agent and memory commands retain streaming, access controls and exact JSON."""

from __future__ import annotations

import json
import shlex
from io import StringIO
from threading import Event
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from datakeel import cli
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, list_runs, prepare_action
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, list_conversations
from datakeel.cli import agent, memory
from datakeel.core.agent_models import ConversationCreate, ModelResponse, ScriptedResponse, ToolCall
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.memory_models import MemoryCreate, MemoryEntry, MemoryPolicy
from datakeel.core.models import JsonDocument, new_id
from datakeel.dataset_store.dataset_service import list_files
from datakeel.delegation.loader import is_read_only_agent, list_agents
from datakeel.delegation.tree import call_tree
from datakeel.memory.service import create_memory, get_memory, list_memories
from tests.agent.conftest import dataset as dataset_fixture
from tests.agent.test_service import action_script
from tests.delegation.test_execution import request as delegation_request
from tests.delegation.test_execution import search
from tests.runtime.test_realtime_streaming import StreamingProvider

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

    from datakeel.core.agent_models import ModelRequest
    from datakeel.datasets.views import DatasetView
    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


pytestmark = pytest.mark.usefixtures("offline_network")
dataset = dataset_fixture


def _parse(arguments: list[str] | str) -> argparse.Namespace:
    return cli.parser().parse_args(
        shlex.split(arguments) if isinstance(arguments, str) else arguments
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ("agent specialists --json", {"agent_command": "specialists"}),
        ("agent list --q abc --dataset d", {"q": "abc", "dataset": "d"}),
        ("agent tree c", {"conversation_id": "c"}),
        ("agent chat hello", {"mode": "auto", "dry_run": False}),
        (
            "agent chat hi --conversation c --mode plan --dataset d --dry-run",
            {"conversation": "c", "mode": "plan", "dataset": "d", "dry_run": True},
        ),
        ("agent resume c --plan p", {"conversation_id": "c", "plan": "p"}),
        (
            "memory list --q abc --dataset d --include-archived",
            {"q": "abc", "dataset": "d", "include_archived": True},
        ),
        ("memory add note --dataset d", {"content": "note", "dataset": "d"}),
        ("memory edit m note", {"memory_id": "m", "content": "note"}),
        ("memory delete m", {"memory_id": "m"}),
    ],
)
def test_command_grammar(arguments: str, expected: dict[str, object]) -> None:
    """Each public subcommand parses its flags and named actors without ambiguity."""
    parsed = vars(_parse(arguments))
    assert parsed.items() >= expected.items()
    if "specialists" not in arguments:
        assert parsed["actor"] == "local"
        named = vars(_parse(arguments + " --actor reader --json"))
        assert named["actor"] == "reader"
        assert named["json_output"] is True


@pytest.mark.parametrize("json_output", [False, True])
def test_specialists(
    db: Database, capsys: pytest.CaptureFixture[str], *, json_output: bool
) -> None:
    """Every bundled contract exposes its real read-only capability and complete tool list."""
    agent.dispatch(db, _parse(["agent", "specialists", *(["--json"] if json_output else [])]))
    output = capsys.readouterr().out
    definitions = list_agents()
    assert len(definitions) == 6
    if json_output:
        assert json.loads(output) == [
            {**item.model_dump(mode="json"), "read_only": is_read_only_agent(item)}
            for item in definitions
        ]
    else:
        assert all(item.name in output for item in definitions)


class LiveOutput(StringIO):
    """Release the blocked model only after its first visible text reaches the terminal."""

    def __init__(self) -> None:
        """Start with an empty capture and a synchronization signal."""
        super().__init__()
        self.visible = Event()

    def write(self, text: str) -> int:
        """Observe actual Rich output while retaining the complete human transcript."""
        count = super().write(text)
        if "Safe streamed answer" in self.getvalue():
            self.visible.set()
        return count


@pytest.mark.parametrize("json_output", [False, True])
def test_chat_streams_before_completion_and_continues_existing_session(
    db: Database, monkeypatch: pytest.MonkeyPatch, *, json_output: bool
) -> None:
    """Live deltas print before provider completion and authoritative text is not duplicated."""
    output = LiveOutput()
    monkeypatch.setattr(agent, "Console", lambda **kwargs: Console(file=output, **kwargs))
    content = "Safe streamed answer with enough text to pass the privacy holdback. " * 4
    fake = FakeProvider([ModelResponse(content=content)])

    def complete(request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        assert emit is not None
        emit(content)
        if not json_output:
            assert output.visible.wait(5), "CLI buffered text until model completion"
        return fake.complete(request)

    agent.dispatch(
        db,
        _parse("agent chat Explain --mode agent" + (" --json" if json_output else "")),
        provider=StreamingProvider(complete),
    )
    conversation = list_conversations(db)[0]
    if json_output:
        report = json.loads(output.getvalue())
        assert report["mode"] == "agent"
        assert report["conversation_id"] == conversation.id
        assert report["events"] == [event.model_dump(mode="json") for event in conversation.events]
        assert [event["event"] for event in report["events"]] == ["text", "done"]
        return
    assert output.getvalue().count(content.strip()) == 1
    assert output.getvalue().endswith(f"Conversation: {conversation.id}\n")
    agent.dispatch(
        db,
        _parse(["agent", "chat", "Continue", "--conversation", conversation.id]),
        provider=FakeProvider([ModelResponse(content="Second turn.")]),
    )
    assert "Second turn." in output.getvalue()
    assert len(list_conversations(db)) == 1
    messages = get_conversation(db, conversation.id).messages
    assert [item.content for item in messages if item.role == "user"] == ["Explain", "Continue"]


def test_chat_dry_run(
    db: Database, dataset: DatasetView, capsys: pytest.CaptureFixture[str]
) -> None:
    """A new dry-run conversation prepares a real plan without changing generated files."""
    agent.dispatch(
        db,
        _parse(
            ["agent", "chat", "Preview", "--dataset", dataset.id, "--dry-run", "--mode", "agent"]
        ),
        provider=FakeProvider(action_script(dataset.id)),
    )
    output = capsys.readouterr().out
    conversation = list_conversations(db)[0]
    assert conversation.config.dry_run
    assert conversation.config.dataset_id == dataset.id
    assert all(
        label in output for label in ("Tool call:", "Tool result:", "Plan:", "Stopped: dry_run")
    )
    assert conversation.pending_plans
    assert list_runs(db) == []
    assert not any(item.metadata.get("quarantined") for item in list_files(db, dataset.id))


def test_agent_list_filters_transcripts_intents_and_actors(
    db: Database, dataset: DatasetView, capsys: pytest.CaptureFixture[str]
) -> None:
    """Multi-term search spans metadata, messages, tool names and planner outcomes."""
    create_conversation(db, ConversationCreate(), actor="outsider")
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(content="Amber result"),
        ]
    )
    agent.dispatch(
        db,
        _parse(["agent", "chat", "Cobalt request", "--dataset", dataset.id]),
        provider=provider,
    )
    view = list_conversations(db, actor="local")[0]
    capsys.readouterr()
    for query in (
        view.id.upper(),
        dataset.id,
        view.config.model.upper(),
        "COBALT amber",
        "LIST_DATASETS",
    ):
        agent.dispatch(
            db,
            _parse(["agent", "list", "--q", query, "--dataset", dataset.id, "--json"]),
        )
        assert [item["id"] for item in json.loads(capsys.readouterr().out)] == [view.id]
    planner = FakeProvider([ScriptedResponse(agent="intent_planner", content='{"kind":"none"}')])
    agent.dispatch(
        db,
        _parse(["agent", "chat", "Unmapped request", "--conversation", view.id, "--mode", "plan"]),
        provider=planner,
    )
    assert "Intent: unsupported" in capsys.readouterr().out
    intent = next(event.intent for event in get_conversation(db, view.id).events if event.intent)
    for query in (intent.kind, intent.text, intent.request):
        agent.dispatch(db, _parse(["agent", "list", "--q", query, "--json"]))
        assert [item["id"] for item in json.loads(capsys.readouterr().out)] == [view.id]
    for flags in (["--q", "absent"], ["--dataset", "missing"], ["--actor", "nobody"]):
        agent.dispatch(db, _parse(["agent", "list", *flags, "--json"]))
        assert json.loads(capsys.readouterr().out) == []
    agent.dispatch(db, _parse(["agent", "list"]))
    assert view.id in capsys.readouterr().out


def test_tree_json_and_human_telemetry_enforce_actor_ownership(
    db: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real delegated call tree aggregates measured parent and specialist activity."""
    provider = FakeProvider(
        [
            search(),
            delegation_request(),
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(content="Child answer"),
            ModelResponse(content="Root answer"),
        ]
    )
    agent.dispatch(db, _parse("agent chat delegate --mode agent"), provider=provider)
    root = list_conversations(db)[0]
    capsys.readouterr()
    expected = call_tree(db, root.id)
    assert len(expected.nodes) == 2
    assert expected.total_tokens > 0
    assert expected.total_tool_calls > 0
    agent.dispatch(db, _parse(["agent", "tree", root.id, "--json"]))
    assert json.loads(capsys.readouterr().out) == expected.model_dump(mode="json")
    agent.dispatch(db, _parse(["agent", "tree", root.id]))
    output = capsys.readouterr().out
    labels = (
        "total_tokens total_cost_usd total_tool_calls total_tool_elapsed_ms "
        "models agent_name agent_path model_calls failed_tools tools"
    )
    assert all(label in output.casefold() for label in labels.split())
    assert "catalog-analyst" in output
    assert str(expected.total_tokens) in output
    with pytest.raises(AuthorizationError, match="another actor"):
        agent.dispatch(db, _parse(["agent", "tree", root.id, "--actor", "outsider"]))


@pytest.mark.parametrize("json_output", [False, True])
def test_resume_approved_plan_prints_receipt(
    db: Database, dataset: DatasetView, capsys: pytest.CaptureFixture[str], *, json_output: bool
) -> None:
    """Resume uses stored approval and returns the actual execution receipt in either format."""
    agent.dispatch(
        db,
        _parse(["agent", "chat", "Delete low quality", "--dataset", dataset.id, "--mode", "agent"]),
        provider=FakeProvider(action_script(dataset.id, "delete_files")),
    )
    view = list_conversations(db)[0]
    plan = view.pending_plans[0]
    capsys.readouterr()
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    args = _parse(
        ["agent", "resume", view.id, "--plan", plan.id, *(["--json"] if json_output else [])]
    )
    agent.dispatch(db, args, provider=FakeProvider([ModelResponse(content="Receipt confirmed.")]))
    output = capsys.readouterr().out
    run = list_runs(db)[0]
    assert run.status == "SUCCEEDED"
    assert len(list_files(db, dataset.id)) == 1
    if json_output:
        report = json.loads(output)
        assert report["conversation_id"] == view.id
        assert report["mode"] == "agent"
        assert report["events"][0]["event"] == "receipt"
        assert report["events"][0]["outcome"]["run"]["id"] == run.id
    else:
        assert f"Receipt: {run.id} SUCCEEDED" in output
        assert output.endswith(f"Conversation: {view.id}\n")


@pytest.mark.parametrize("json_output", [False, True])
def test_memory_crud_redacts_and_searches_bilingual_identifiers(
    db: Database, dataset: DatasetView, capsys: pytest.CaptureFixture[str], *, json_output: bool
) -> None:
    """Both output modes preserve PII redaction, scope and searchable bilingual identifiers."""
    flags = ["--json"] if json_output else []
    content = "Metric invoice_2026 营收定义 contact user@example.org"
    memory.dispatch(db, _parse(["memory", "add", content, "--dataset", dataset.id, *flags]))
    output = capsys.readouterr().out
    entry = list_memories(db)[0]
    assert entry.content == "Metric invoice_2026 营收定义 contact [REDACTED]"
    assert "user@example.org" not in output
    assert entry.id in output
    if json_output:
        assert MemoryEntry.model_validate_json(output).id == entry.id
    for query in ("INVOICE_2026", "营收", "metric 营收"):
        memory.dispatch(
            db,
            _parse(["memory", "list", "--q", query, "--dataset", dataset.id, *flags]),
        )
        assert entry.id in capsys.readouterr().out
    memory.dispatch(
        db,
        _parse(["memory", "edit", entry.id, "Updated 联系 +1 (415) 555-0123", *flags]),
    )
    output = capsys.readouterr().out
    assert get_memory(db, entry.id).content == "Updated 联系 [REDACTED]"
    assert "555-0123" not in output
    assert entry.id in output
    memory.dispatch(db, _parse(["memory", "delete", entry.id, *flags]))
    output = capsys.readouterr().out
    assert entry.id in output
    assert list_memories(db) == []
    if json_output:
        assert json.loads(output)["deleted_ids"] == [entry.id]
    with pytest.raises(NotFoundError):
        get_memory(db, entry.id)


def test_memory_archived_list_and_empty_entrypoint(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Command registration reaches real storage and archival inclusion is explicit."""
    invoke("memory", "list")
    assert "memor" in capsys.readouterr().out.lower()
    for _ in range(2):
        create_memory(
            db, MemoryCreate(content="Repeated revenue metric"), policy=MemoryPolicy(max_entries=1)
        )
    memory.dispatch(db, _parse(["memory", "list", "--include-archived", "--json"]))
    entries = json.loads(capsys.readouterr().out)
    assert len(entries) == 2
    assert sum(item["archived"] for item in entries) == 1
    invoke("agent", "specialists", "--json")
    assert len(json.loads(capsys.readouterr().out)) == 6


def test_memory_delete_requires_named_actor_write_scope(db: Database) -> None:
    """Read-only registered actors cannot exploit the lower-level actorless deletion API."""
    entry = create_memory(db, MemoryCreate(content="Retain this memory"))
    for user, roles in (("local", []), ("observer", ["acceptance"])):
        plan = prepare_action(
            db,
            "manage_users",
            JsonDocument(
                {"request_id": new_id(), "operation": "create", "user_id": user, "role_ids": roles}
            ),
        )
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with pytest.raises(AuthorizationError):
        memory.dispatch(db, _parse(["memory", "delete", entry.id, "--actor", "observer"]))
    assert get_memory(db, entry.id).content == entry.content


def test_chat_stream_reset_restores_text_fallback(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Retries reset only their own path and never hide a later complete answer."""
    events = [
        AgentEvent(event="text_delta", text="Partial attempt"),
        AgentEvent(event="text_delta", text=""),
        AgentEvent(event="text_delta", text="Child stream", agent_path="main/child"),
        AgentEvent(event="text", text="Recovered answer"),
        AgentEvent(event="text", text="Child stream", agent_path="main/child"),
        AgentEvent(event="done"),
    ]
    monkeypatch.setattr(
        "datakeel.agent.service.send_message", lambda *_args, **_kwargs: iter(events)
    )
    agent.dispatch(db, _parse("agent chat retry"))
    output = capsys.readouterr().out
    assert "Recovered answer" in output
    assert output.count("Child stream") == 1
    agent.dispatch(db, _parse("agent list --actor missing"))
    assert "No conversations" in capsys.readouterr().out
