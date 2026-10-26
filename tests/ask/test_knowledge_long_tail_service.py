# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify long-tail dependency questions through persistent production answers."""

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("出货额有谁在使用?", "downstream"),
        ("出货额停掉以后\uff0c哪些表会受到影响?", "downstream"),
        ("Where does shipment_amount end up?", "downstream"),
        ("shipment_amount is being read by which reports?", "downstream"),
        ("What ends up in shipment_amount?", "upstream"),
        ("出货额不再读取哪些表?", "upstream"),
        ("What is consumed by shipment_amount?", "upstream"),
        ("Who owns shipment_amount if it went away?", "owner"),
    ],
)
def test_long_tail_answers_preserve_knowledge_without_numeric_fallback(
    db: Database, enterprise_sample: EnterpriseSample, question: str, intent: str
) -> None:
    """Even a missing dependency is a persisted knowledge result with no scalar guess."""
    answer = ask_data(db, AskRequest(question=question))
    assert answer.answer_kind == "knowledge"
    assert answer.result is None
    assert answer.sql is None
    assert answer.knowledge is not None
    assert answer.knowledge.intent == intent
    assert answer.status in {"answered", "unanswerable"}
    assert get_answer(db, answer.id) == answer
