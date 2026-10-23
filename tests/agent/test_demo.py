# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The default offline demo drives actual searches, frozen actions, and receipts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.service import list_runs
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def test_demo_when_quarantine_and_new_version_requested_executes_both_actions(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Demonstrate the specified Chinese conversation using generated low-quality assets."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    events = list(
        send_message(
            db, conversation.id, MessageInput(content="把质量低于 60 分的文本样本隔离并生成新版本")
        )
    )
    assert {run.action_type for run in list_runs(db)} == {
        "quarantine_files",
        "create_version_from_selection",
    }
    assert sum(event.event == "receipt" for event in events) == 2
    assert events[-2].text == "已隔离所选样本并生成新版本。执行回执已保存。"


@pytest.mark.parametrize(
    "content",
    [
        "list datasets",
        "quality",
        "report",
        "lineage",
        "search files",
        "unquarantine",
        "pipeline",
        "export",
        "delete",
    ],
)
def test_demo_when_supported_intent_requested_returns_a_complete_event_stream(
    db: Database,
    dataset: DatasetView,
    content: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep every disclosed demo command offline while using real domain services."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    conversation = create_conversation(db, ConversationCreate())
    events = list(send_message(db, conversation.id, MessageInput(content=content)))
    assert events[-1].event == "done"
    assert not any(event.stop_reason in {"budget_exceeded", "provider_error"} for event in events)


def test_demo_when_no_assets_exist_lists_empty_workspace(db: Database) -> None:
    """Keep a fresh installation useful before the first generated dataset is imported."""
    conversation = create_conversation(db, ConversationCreate())
    events = list(send_message(db, conversation.id, MessageInput(content="list datasets")))
    assert events[-2].text == "已列出当前数据集。"


def test_demo_when_default_budget_used_supports_search_quarantine_and_delete_approval(
    db: Database,
    dataset: DatasetView,
) -> None:
    """Reserve deterministic offline usage accurately throughout the documented conversation."""
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    for content in [
        "Find text files with quality below 60",
        "Quarantine those files and create a version",
        "Delete those files",
    ]:
        events = list(send_message(db, conversation.id, MessageInput(content=content)))
        assert not any(event.stop_reason == "budget_exceeded" for event in events)
    assert events[-2].stop_reason == "approval_required"
    assert len(list_runs(db)) == 2
