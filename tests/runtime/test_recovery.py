# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real process death preserves controlled action and tool-call exactly-once evidence."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan, list_runs
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput
from datakeel.harness.service import list_accounts, list_traces
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.tool_invocations import list_invocations
from tests.runtime.recovery_process import ProcessRequest, action_script

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _request(db: Database, tmp_path: Path) -> ProcessRequest:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    healthy = tmp_path / "healthy.txt"
    healthy.write_text("Generated healthy content with enough information.", encoding="utf-8")
    dataset = import_paths(db, "crash-fixture", [empty, healthy])
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    with db.session() as session:
        schema = (
            None if db.sqlite else session.execute(text("SELECT current_schema()")).scalar_one()
        )
    return ProcessRequest(
        database_url=db.engine.url.render_as_string(hide_password=False),
        schema_name=schema,
        conversation_id=conversation.id,
        dataset_id=dataset.id,
        phase="pause",
        marker=tmp_path / "crash.marker",
        result=tmp_path / "result.jsonl",
    )


def _run(request: ProcessRequest) -> subprocess.CompletedProcess[str]:
    path = request.result.with_suffix(".request.json")
    path.write_text(request.model_dump_json(), encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_", "LANGSMITH_", "LANGCHAIN_")
        )
    }
    environment["DATAKEEL_HOME"] = str(request.result.parent / "home")
    return subprocess.run(  # noqa: S603  # Fixed test module and generated request file; no shell.
        [sys.executable, "-m", "tests.runtime.recovery_process", str(path)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _approve(db: Database, request: ProcessRequest) -> ProcessRequest:
    checkpoint = SQLAlchemySaver(db).get_tuple(
        {"configurable": {"thread_id": request.conversation_id}}
    )
    assert checkpoint is not None
    assert any(channel == "__interrupt__" for _, channel, _ in checkpoint.pending_writes)
    plan_id = checkpoint.checkpoint["channel_values"]["plan_id"]
    plan = get_plan(db, plan_id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return request.model_copy(update={"plan_id": plan.id})


def _assert_recovered(
    db: Database,
    request: ProcessRequest,
    process: subprocess.CompletedProcess[str],
) -> None:
    invocations = list_invocations(db, request.conversation_id)
    counts = Counter(item.name for item in invocations)
    assert counts["delete_files"] == 1
    assert counts["tool_search"] == 1
    assert all(count == 1 for count in counts.values())
    runs = [run for run in list_runs(db) if run.plan_id == request.plan_id]
    assert len(runs) == 1
    assert runs[0].status == "SUCCEEDED"
    assert process.returncode == 0, process.stderr
    events = [
        AgentEvent.model_validate_json(line) for line in request.result.read_text().splitlines()
    ]
    assert events[-1].event == "done"
    receipts = [item.outcome.run for item in events if item.event == "receipt" and item.outcome]
    assert [item.id for item in receipts if item] == [runs[0].id]
    conversation = get_conversation(db, request.conversation_id)
    assert len([item for item in conversation.messages if item.role == "user"]) == 1
    results = Counter(item.tool_call_id for item in conversation.messages if item.role == "tool")
    assert results == {"discover-action": 1, "delete-selection": 1}
    traces = list_traces(db, request.conversation_id)
    assert len(traces) == 3
    assert all(
        sum(part.tokens for part in item.segments) == item.usage.input_tokens for item in traces
    )
    account = next(
        item for item in list_accounts(db) if item.key == f"conversation:{request.conversation_id}"
    )
    assert account.used_tokens == sum(item.accounted_tokens for item in traces)
    assert account.reserved_tokens == 0


def test_recovery_when_killed_after_interrupt_preserves_one_action_and_tool_call(
    db: Database,
    tmp_path: Path,
) -> None:
    """A fresh process resumes a durable interrupt after an ungraceful response-owner death."""
    request = _request(db, tmp_path)
    killed = _run(request)
    assert killed.returncode == -signal.SIGKILL, killed.stderr
    assert request.marker.read_text() == "pause"
    assert list_runs(db) == []
    request = _approve(db, request).model_copy(update={"phase": "resume"})
    _assert_recovered(db, request, _run(request))


def test_recovery_when_killed_after_execution_commit_reuses_run_before_checkpoint(
    db: Database,
    tmp_path: Path,
) -> None:
    """Replay the execute node after its committed action without running that action again."""
    request = _request(db, tmp_path)
    list(
        send_message(
            db,
            request.conversation_id,
            MessageInput(content="Delete selected empty files"),
            provider=FakeProvider(action_script(request.dataset_id)),
        )
    )
    request = _approve(db, request).model_copy(update={"phase": "resume_commit"})
    killed = _run(request)
    assert killed.returncode == -signal.SIGKILL, killed.stderr
    assert request.marker.read_text() == "resume_commit"
    committed = [run.id for run in list_runs(db) if run.plan_id == request.plan_id]
    assert len(committed) == 1
    request = request.model_copy(update={"phase": "resume"})
    _assert_recovered(db, request, _run(request))
    assert [run.id for run in list_runs(db) if run.plan_id == request.plan_id] == committed
