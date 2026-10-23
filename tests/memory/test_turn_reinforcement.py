# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Model calls and delegated graphs share one reinforcement per real user question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, resume_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelResponse,
    ResumeInput,
    ToolCall,
)
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import JsonDocument
from datakeel.memory.service import create_memory, get_memory
from datakeel.storage.dataset_service import import_paths
from tests.agent.test_resume import pause_deletion
from tests.delegation.test_execution import search
from tests.memory.helpers import freeze_memory_clock

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_memory_when_three_model_calls_share_question_strengthens_once(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every prompt and response use stays visible while the stored strength rises by 0.5."""
    clock = freeze_memory_clock(monkeypatch)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=clock)
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider(
        [
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(content="Reviewed."),
        ]
    )
    events = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert len(provider.requests) == 3
    assert all(entry.content in request.model_dump_json() for request in provider.requests)
    assert events[-1].used_memory_ids == [entry.id]
    used = get_memory(db, entry.id, clock=clock)
    assert used.strength == 1.5
    assert used.last_used_at == clock.now


def test_memory_when_child_uses_parent_memory_strengthens_once_for_root_question(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A specialist's isolated transcript cannot create another reinforcement entitlement."""
    clock = freeze_memory_clock(monkeypatch)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=clock)
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider(
        [
            search(),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        name="delegate_agent",
                        arguments=JsonDocument(
                            {"agent": "catalog-analyst", "task": "Explain revenue metric"}
                        ),
                    )
                ]
            ),
            ModelResponse(content="Specialist reviewed."),
            ModelResponse(content="Reviewed."),
        ]
    )
    events = list(
        send_message(db, conversation.id, MessageInput(content="revenue metric"), provider=provider)
    )
    assert len(provider.requests) == 4
    child = next(request for request in provider.requests if request.agent_path != "main")
    assert entry.content in child.model_dump_json()
    assert all(entry.content in request.model_dump_json() for request in provider.requests)
    assert events[-1].used_memory_ids == [entry.id]
    used = get_memory(db, entry.id, clock=clock)
    assert used.strength == 1.5
    assert used.last_used_at == clock.now


def test_memory_when_next_user_question_reuses_memory_strengthens_again(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new user turn, even with identical text, receives its own one-time increment."""
    clock = freeze_memory_clock(monkeypatch)
    entry = create_memory(db, MemoryCreate(content="revenue metric guidance"), clock=clock)
    conversation = create_conversation(db, ConversationCreate())
    for strength in (1.5, 2.0):
        provider = FakeProvider(
            [
                ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
                ModelResponse(content="Reviewed."),
            ]
        )
        events = list(
            send_message(
                db, conversation.id, MessageInput(content="revenue metric"), provider=provider
            )
        )
        assert len(provider.requests) == 2
        assert events[-1].used_memory_ids == [entry.id]
        used = get_memory(db, entry.id, clock=clock)
        assert used.strength == strength
        assert used.last_used_at == clock.now


def test_memory_when_approval_resumes_question_does_not_strengthen_again(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new response lease after approval still belongs to the original user question."""
    clock = freeze_memory_clock(monkeypatch)
    entry = create_memory(
        db, MemoryCreate(content="Delete low quality files guidance"), clock=clock
    )
    file = tmp_path / "empty.txt"
    file.write_text("", encoding="utf-8")
    dataset = import_paths(db, "memory-resume-fixture", [file])
    conversation_id, plan = pause_deletion(db, dataset.id)
    assert get_memory(db, entry.id, clock=clock).strength == 1.5
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    provider = FakeProvider([ModelResponse(content="Approved deletion completed.")])
    events = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="memory-resume"),
            provider=provider,
        )
    )
    assert len(provider.requests) == 1
    assert entry.content in provider.requests[0].model_dump_json()
    assert events[-1].used_memory_ids == [entry.id]
    used = get_memory(db, entry.id, clock=clock)
    assert used.strength == 1.5
    assert used.last_used_at == clock.now
