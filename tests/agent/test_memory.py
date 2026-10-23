# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Memory resolves human decisions from facts and exposes no cross-session history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.agent.memory import cross_session_memory, workspace
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.conversation_store import get
from tests.agent.test_service import action_script

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def test_memory_when_human_rejects_plan_removes_pending_card_and_keeps_decision(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Feed the latest rejection into volatile context without losing historical plan evidence."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="delete"),
            provider=FakeProvider(action_script(dataset.id, "delete_files")),
        )
    )
    plan = get_conversation(db, conversation.id).pending_plans[0]
    approve_plan(db, plan.id, ApprovalDecision(approve=False, plan_digest=plan.plan_digest))
    assert get_conversation(db, conversation.id).pending_plans == []
    assert "REJECTED" in workspace(db, get(db, conversation.id)).model_dump_json()
    assert cross_session_memory() == []


def test_memory_when_action_completes_keeps_full_plan_once_and_summarizes_workspace(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Reduce repeated context without dropping the frozen manifest or execution receipt."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="quarantine"),
            provider=FakeProvider(action_script(dataset.id)),
        )
    )
    stored = get(db, conversation.id)
    message = next(item for item in stored.messages if item.name == "quarantine_files")
    outcome = ToolOutcome.model_validate_json(message.content)
    assert outcome.content.root == {}
    assert outcome.plan is not None
    assert outcome.plan.manifest.objects
    assert outcome.run is not None
    assert outcome.run.receipt is not None
    facts = workspace(db, stored).root["plans"]
    assert isinstance(facts, list)
    assert facts == [
        {
            "plan_id": outcome.plan.id,
            "action_type": "quarantine_files",
            "status": "EXECUTED",
            "requires_approval": False,
            "run": {
                "id": outcome.run.id,
                "status": "SUCCEEDED",
                "task_id": None,
                "has_receipt": True,
            },
        }
    ]
