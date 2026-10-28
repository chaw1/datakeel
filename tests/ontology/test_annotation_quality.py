# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotation reads retain identity, enforce typed arguments and answer using actual metrics."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from datakeel.agent.demo import DemoProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.agent.tools import deferred_tools, resident_tools
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelRequest
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.harness.annotation_cases import seed_annotation_qa_demo
from datakeel.ontology.annotation_demo import respond_annotation_quality
from datakeel.ontology.functions import invoke_function
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths


def test_annotation_read_is_deferred_version_scoped_and_has_no_business_writes(
    db: Database, tmp_path: Path
) -> None:
    """Queries return the stored report and exact source version without new inspection facts."""
    summary = seed_annotation_qa_demo(db, tmp_path)
    arguments = JsonDocument({"dataset_id": summary.dataset_id, "version_id": summary.version_id})
    first = invoke_function(db, "annotation_quality", arguments)
    second = invoke_function(db, "annotation_quality", arguments)
    assert first == second
    assert first.asset_refs[0].asset_id == summary.dataset_id
    assert first.asset_refs[0].version == summary.version_id
    assert "annotation_quality" not in {tool.name for tool in resident_tools()}
    assert "annotation_quality" in {tool.name for tool in deferred_tools()}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        invoke_function(
            db,
            "annotation_quality",
            JsonDocument(
                {
                    "dataset_id": summary.dataset_id,
                    "execute": True,
                }
            ),
        )
    with pytest.raises(NotFoundError):
        invoke_function(
            db,
            "annotation_quality",
            JsonDocument(
                {
                    "dataset_id": summary.dataset_id,
                    "version_id": "missing",
                }
            ),
        )


def test_offline_agent_answers_annotation_question_with_measured_agreement(
    db: Database, tmp_path: Path
) -> None:
    """The displayed answer derives its numeric value from the saved report tool response."""
    summary = seed_annotation_qa_demo(db, tmp_path)
    conversation = create_conversation(db, ConversationCreate(dataset_id=summary.dataset_id))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="这批标注一致性怎么样?"),
            provider=DemoProvider(),
        )
    )
    assert [event.call.name for event in events if event.call] == [
        "tool_search",
        "annotation_quality",
    ]
    answers = [event.text for event in events if event.event == "text"]
    assert len(answers) == 1
    assert "Fleiss κ = 1.0000" in (answers[0] or "")
    assert "疑似错标 1 条" in (answers[0] or "")


def test_offline_annotation_question_without_imported_panel_explains_missing_report(
    db: Database, tmp_path: Path
) -> None:
    """An empty history cannot be presented as perfect agreement."""
    path = tmp_path / "note.txt"
    path.write_text("Generated note.")
    dataset = import_paths(db, "Empty annotation history", [path])
    conversation = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="annotation quality"),
            provider=DemoProvider(),
        )
    )
    assert any("没有标注质量报告" in (event.text or "") for event in events)


def test_demo_intent_requires_dataset_and_leaves_other_questions_alone() -> None:
    """Offline intent does not invent a dataset or consume unrelated user messages."""
    request = ModelRequest(model="fake-script", messages=[], tools=[], segments=[])
    response = respond_annotation_quality(request, "annotation agreement", JsonDocument({}), [])
    assert response is not None
    assert "选择" in response.content
    assert respond_annotation_quality(request, "hello", JsonDocument({}), []) is None
