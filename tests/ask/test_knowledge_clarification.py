# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist and replay intent choices without losing the original subject or question."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.knowledge_models import KnowledgeAnswer
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database


def test_intent_clarification_reasks_the_same_question_and_subject(
    db: Database, tmp_path: Path
) -> None:
    """A same-type question offers directions and a selected direction produces evidence."""
    seed_enterprise_kg(db, tmp_path)
    request = AskRequest(question="orders 对应哪些表")
    unresolved = ask_data(db, request)
    assert unresolved.answer_kind == "knowledge"
    assert unresolved.status == "clarification"
    assert unresolved.knowledge is not None
    assert unresolved.knowledge.reason_code == "ambiguous_intent"
    assert unresolved.knowledge.intent_candidates == ("upstream", "downstream")
    assert unresolved.knowledge.subject is not None
    assert unresolved.recognition is not None
    assert unresolved.recognition.rule_id == "K8-ambiguous-intent"
    assert get_answer(db, unresolved.id) == unresolved
    selected = ask_data(
        db,
        request.model_copy(
            update={
                "subject_id": unresolved.knowledge.subject.asset_ref.asset_id,
                "knowledge_intent": "downstream",
                "session_id": unresolved.session_id,
            }
        ),
    )
    assert selected.question == request.question
    assert selected.status == "answered"
    assert selected.knowledge is not None
    assert selected.knowledge.intent == "downstream"
    assert selected.knowledge.subject == unresolved.knowledge.subject
    assert selected.result is None
    assert selected.assertions


def test_related_is_not_an_interactive_knowledge_intent() -> None:
    """The aggregate related view is reserved for optional numeric answer context."""
    with pytest.raises(ValidationError) as failure:
        AskRequest.model_validate({"question": "orders", "knowledge_intent": "related"})
    assert failure.value.errors()[0]["type"] == "literal_error"
    assert failure.value.errors()[0]["loc"] == ("knowledge_intent",)
    schema = AskRequest.model_json_schema()["properties"]["knowledge_intent"]
    assert schema["anyOf"][0]["enum"] == ["owner", "upstream", "downstream", "owned"]
    assert KnowledgeAnswer(intent="related").intent == "related"
