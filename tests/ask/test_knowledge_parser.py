# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual interrogatives generalize while numeric questions retain their route."""

import pytest

from datakeel.ask.knowledge_parser import parse_knowledge_question


@pytest.mark.parametrize(
    ("question", "intent", "subject"),
    [
        ("出货额谁负责?", "owner", "出货额"),
        ("负责出货额的是谁", "owner", "出货额"),
        ("出货额的维护人是谁", "owner", "出货额"),
        ("orders 被哪些指标使用", "downstream", "orders"),
        ("请问出货额的负责人是谁呢?", "owner", "出货额"),
        ("出货额由谁维护", "owner", "出货额"),
        ("出货额归谁管", "owner", "出货额"),
        ("Who maintains the sales table?", "owner", "sales table"),
        ("Who is responsible for customer_count?", "owner", "customer_count"),
        ("owner of SALES", "owner", "SALES"),
        ("库存量从哪里来的?", "upstream", "库存量"),
        ("零售额是基于哪张表算的?", "upstream", "零售额"),
        ("出货量由什么计算", "upstream", "出货量"),
        ("inventory 的上游有哪些", "upstream", "inventory"),
        ("Where does the revenue metric come from?", "upstream", "revenue metric"),
        ("What is sales_summary derived from?", "upstream", "sales_summary"),
        ("upstream of crm/main/sales", "upstream", "crm/main/sales"),
        ("哪些指标依赖 orders 表", "downstream", "orders 表"),
        ("orders 表的下游有哪些", "downstream", "orders 表"),
        ("What uses the sales table?", "downstream", "sales table"),
        ("Which metrics are computed from orders?", "downstream", "orders"),
        ("downstream of sales_summary", "downstream", "sales_summary"),
        ("周岩负责哪些", "owned", "周岩"),
        ("供应链负责人维护哪些表", "owned", "供应链负责人"),
        ("What does Priya Natarajan own?", "owned", "Priya Natarajan"),
        ("Which tables does the Finance team maintain?", "owned", "Finance team"),
    ],
)
def test_interrogatives_capture_subject_without_full_question_noise(
    question: str,
    intent: str,
    subject: str,
) -> None:
    """Sentence structure selects direction independently of the registered vocabulary."""
    parsed = parse_knowledge_question(question)
    assert parsed is not None
    assert (parsed.intent, parsed.subject) == (intent, subject)


@pytest.mark.parametrize(
    "question",
    [
        "上个季度华东区基于开票的销售额是多少",
        "2026年3月来源于线上的零售额是多少",
        "2026年3月用到优惠券的成交订单数是多少",
        "华东区负责的客户数量是多少",
        "2026年3月下游渠道的出货额是多少",
        "2026年3月维护期内的维修费用是多少",
        "How much revenue came from online orders in March?",
        "Show sales for downstream channels",
        "Who owns?",
        "谁负责",
    ],
)
def test_non_interrogative_relationship_words_do_not_steal_metric_route(question: str) -> None:
    """Only a complete supported relationship question enters knowledge resolution."""
    assert parse_knowledge_question(question) is None
