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


def test_person_focus_with_unfamiliar_verb_answers_owner_without_metric_values(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """An unfamiliar relationship verb still uses the registered subject and requested person."""
    answer = ask_data(db, AskRequest(question="出货额该找谁拍板"))
    assert answer.answer_kind == "knowledge"
    assert answer.status == "answered"
    assert answer.result is None
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code is None
    assert answer.knowledge.intent == "owner"
    assert answer.knowledge.system_records


def test_ambiguous_intent_cannot_fall_back_to_metric_values(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A recognized subject with an unresolved relationship asks for an intent, never a value."""
    answer = ask_data(db, AskRequest(question="出货额有哪些?"))
    assert answer.answer_kind == "knowledge"
    assert answer.status == "clarification"
    assert answer.result is None
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code == "ambiguous_intent"
    assert answer.knowledge.intent_candidates == ("upstream", "downstream", "owner")


def test_requested_person_cannot_fall_back_to_metric_values(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Explicitly requesting a person is a hard guard against returning the metric's number."""
    answer = ask_data(db, AskRequest(question="出货额由哪位同事保管"))
    assert answer.answer_kind == "knowledge"
    assert answer.result is None
    assert answer.knowledge is not None
    assert answer.knowledge.intent == "owner"


@pytest.mark.parametrize(
    ("question", "status", "reason"),
    [
        ("出货额谁负责", "answered", None),
        ("营业额谁负责", "clarification", "ambiguous_subject"),
        ("unregistered_metric 谁负责", "unanswerable", "unknown_subject"),
        ("谁?", "unanswerable", "unknown_subject"),
        ("出货额有哪些?", "clarification", "ambiguous_intent"),
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
