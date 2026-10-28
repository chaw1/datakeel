# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Classified write workflows keep reads available and wait for explicit user starts."""

from pathlib import Path

import pytest

from datakeel.actions.service import list_approvals, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.runtime.workflow_service import start_workflow
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.task_queries import list_tasks
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_store import list_runs as list_workflow_runs
from tests.workflows.conftest import worker_hooks


def _write_attempt(dataset_id: str) -> FakeProvider:
    return FakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(name="tool_search", arguments=JsonDocument({"query": "run_pipeline"}))
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        name="get_quality", arguments=JsonDocument({"dataset_id": dataset_id})
                    ),
                    ToolCall(
                        name="run_pipeline", arguments=JsonDocument({"dataset_id": dataset_id})
                    ),
                    ToolCall(name="list_datasets"),
                ]
            ),
        ]
    )


def test_classified_write_when_model_calls_action_stops_before_mutation_then_user_can_start(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A normal model reply cannot execute a classified write before the user's form start."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    source = tmp_path / "sample.txt"
    source.write_text("Generated text for a local workflow confirmation test.")
    dataset = import_paths(db, "confirmation", [source])
    conversation = create_conversation(
        db, ConversationCreate(dataset_id=dataset.id, model="fake-script")
    )
    provider = _write_attempt(dataset.id)
    request = MessageInput(content="Give this dataset a comprehensive assessment.")
    events = list(send_message(db, conversation.id, request, provider=provider))
    route = next(event.route for event in events if event.event == "route")
    assert route is not None
    assert route.requires_confirmation
    assert route.classifier_selection == "dataset-health"
    assert any(event.stop_reason == "workflow_confirmation_required" for event in events)
    assert [item.name for item in list_invocations(db, conversation.id)] == [
        "tool_search",
        "get_quality",
    ]
    assert list_runs(db) == list_approvals(db) == list_tasks(db) == list_workflow_runs(db) == []
    transcript = get_conversation(db, conversation.id).messages
    assert [item.name for item in transcript if item.role == "tool"] == [
        "tool_search",
        "get_quality",
        "run_pipeline",
        "list_datasets",
    ]
    assert list(send_message(db, conversation.id, request, provider=provider)) == events
    run = list(
        start_workflow(
            db,
            "dataset-health",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="user-confirmed"
            ),
            hooks=worker_hooks(db),
        )
    )[-1].run
    assert run.status == "SUCCEEDED"
    assert [item.action_type for item in list_runs(db)] == ["run_pipeline"]


@pytest.mark.parametrize("tool", ["delegate_agent", "write_memory", "execute_plan"])
def test_classified_write_when_model_attempts_indirect_mutation_also_stops(
    db: Database, tool: str
) -> None:
    """Delegation and separate write channels cannot bypass the response confirmation gate."""
    conversation = create_conversation(db, ConversationCreate(model="fake-script"))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Give this dataset a comprehensive assessment."),
            provider=FakeProvider([ModelResponse(tool_calls=[ToolCall(name=tool)])]),
        )
    )
    assert any(event.stop_reason == "workflow_confirmation_required" for event in events)
    assert list_invocations(db, conversation.id) == []
    assert list_runs(db) == list_workflow_runs(db) == []
