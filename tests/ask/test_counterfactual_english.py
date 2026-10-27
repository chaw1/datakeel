# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""English counterfactual consequences point downstream; requests for a replacement point up."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from tests.ask.parsing_helpers import registered_question

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "question",
    [
        "If the inventory table went away, what would break?",
        "If inventory disappeared, what stops working?",
        "If inventory were dropped, who is affected?",
        "If inventory is removed, who would be affected?",
        "What breaks if inventory goes away?",
        "What stops working if inventory is retired?",
        "Who is affected if inventory is shut down?",
        "Who would be hurt if inventory went offline?",
        "If inventory vanished, what would fail?",
        "Suppose inventory went away; what would break?",
        "If inventory were turned off, which reports would stop working?",
        "If inventory stopped updating, who would notice?",
        "If inventory had an outage, what would be affected downstream?",
        "如果 inventory 没了, 什么会坏?",
    ],
)
def test_consequences_of_losing_a_subject_are_downstream(question: str) -> None:
    """Breakage, stopped work and affected parties are consumers of the missing subject."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == "downstream", (question, parsed.recognition.rule_id)


@pytest.mark.parametrize(
    "question",
    [
        "If inventory went away, where would its data come from?",
        "If inventory went away, what would it need instead?",
        "What would break inventory if it went away?",
        "If its source went away, would inventory break?",
    ],
)
def test_replacement_sources_and_causes_of_breakage_stay_upstream(question: str) -> None:
    """Asking what feeds or breaks the subject is an upstream question in the same frame."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == "upstream", (question, parsed.recognition.rule_id)


def test_metric_counterfactual_in_chinese_keeps_downstream() -> None:
    """The Chinese consequence frame is unchanged by the English additions."""
    parsed = registered_question("如果退款额不再更新, 会影响到哪些报表?", "退款额")
    assert parsed is not None
    assert parsed.intent == "downstream"


@pytest.mark.parametrize(
    "question",
    [
        "If the orders table went away, what would break?",
        "If the payments table were dropped, what would stop working?",
        "Who would be affected if the tickets table was deleted?",
    ],
)
def test_counterfactual_table_questions_answer_with_knowledge_not_numbers(
    db: Database, enterprise_sample: EnterpriseSample, question: str
) -> None:
    """The shipped catalog answers these as lineage knowledge and never returns a metric value."""
    assert enterprise_sample.sources
    answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
    assert answer.answer_kind == "knowledge", answer.message
    assert answer.status == "answered", answer.message
    assert answer.result is None
    assert answer.knowledge is not None
    assert answer.knowledge.intent == "downstream"
