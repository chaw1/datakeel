# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit every knowledge outcome and explain unresolved document associations."""

from pathlib import Path

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import list_assertions


def test_unsupported_knowledge_question_cannot_fall_back_to_metric_values(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A recognized metric name cannot turn an unsupported who-question into a numeric answer."""
    answer = ask_data(db, AskRequest(question="出货额该找谁拍板"))
    assert answer.answer_kind == "knowledge"
    assert answer.status == "unanswerable"
    assert answer.result is None
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code == "unsupported_phrasing"


@pytest.mark.parametrize(
    ("question", "status", "reason"),
    [
        ("出货额谁负责", "answered", None),
        ("营业额谁负责", "clarification", "ambiguous_subject"),
        ("unregistered_metric 谁负责", "unanswerable", "unknown_subject"),
        ("谁?", "unanswerable", "unsupported_phrasing"),
        ("Grace Liu 负责哪些?", "unanswerable", "pending_links"),
    ],
)
def test_knowledge_outcomes_have_persistent_audit_assertions(
    db: Database, tmp_path: Path, question: str, status: str, reason: str | None
) -> None:
    """Successful, ambiguous, unknown and unsupported questions all retain question-bound facts."""
    seed_enterprise_kg(db, tmp_path)
    answer = ask_data(db, AskRequest(question=question))
    assert answer.answer_kind == "knowledge"
    assert answer.status == status
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code == reason
    assert answer.assertions
    assert get_answer(db, answer.id) == answer
    assert {item.id for item in list_assertions(db, answer.id)} == {
        item.id for item in answer.assertions
    }
    if status != "answered":
        unresolved = next(
            item for item in answer.assertions if item.predicate == "ask.knowledge_unresolved"
        )
        assert unresolved.reason == reason
    if reason == "pending_links":
        assert answer.knowledge.pending_ambiguous_links == 1
        assert "有 1 条文档说法的关联待确认" in answer.message
        assert "都没有登记" not in answer.message
