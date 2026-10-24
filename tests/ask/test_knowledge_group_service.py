# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Grouping modifiers must not erase a main catalog or ownership question."""

import pytest

from datakeel.ask import service
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import CompiledQuery, QueryResult
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database


def _forbid_query(_connection: str, _query: CompiledQuery) -> QueryResult:
    pytest.fail("A grouping modifier must not turn a knowledge question into a metric query")


@pytest.mark.parametrize(
    ("question", "identity", "intent"),
    [
        ("按渠道汇总的开票销售额来自哪些表\uff1f", "sales_amount", "upstream"),
        ("零售额按品类统计的口径归谁维护\uff1f", "retail_revenue", "owner"),
        ("订单数按渠道展示的这个指标由谁负责\uff1f", "order_count", "owner"),
        ("维修费用按区域统计的口径由哪个团队负责\uff1f", "repair_cost", "owner"),
    ],
)
def test_grouping_modifier_preserves_knowledge_main_question_without_sql(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    identity: str,
    intent: str,
) -> None:
    """Registered synthetic sources remain available, but these questions never execute SQL."""
    monkeypatch.setattr(service, "execute_query", _forbid_query)
    answer = ask_data(db, AskRequest(question=question))
    assert answer.answer_kind == "knowledge"
    assert answer.result is None
    assert answer.sql is None
    assert answer.knowledge is not None
    assert answer.knowledge.subject is not None
    assert answer.knowledge.subject.asset_ref.asset_id == identity
    assert answer.knowledge.intent == intent
    assert get_answer(db, answer.id) == answer
