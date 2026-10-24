# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure development cases distinguish directory cardinality from business measurements."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent", "target"),
    [
        ("inventory 一共供几个报表消费", "inventory", "downstream", "view"),
        ("inventory 一共给几个指标当输入", "inventory", "downstream", "metric"),
        ("inventory 是多少个指标的基础", "inventory", "downstream", "metric"),
        ("inventory_units 所依赖的表有几张", "inventory_units", "upstream", "table"),
        ("inventory_units 的来源表总共有多少", "inventory_units", "upstream", "table"),
        ("inventory_units 来源于几张由团队维护的表", "inventory_units", "upstream", "table"),
        ("inventory 一共有几个维护指标的团队负责", "inventory", "owner", "team"),
        ("维护 inventory 的人有几个", "inventory", "owner", "person"),
        ("inventory 衍生出来的汇总一共有几份", "inventory", "downstream", "view"),
        ("以 inventory 为输入的指标数量是多少", "inventory", "downstream", "metric"),
        ("How many related metrics does inventory feed?", "inventory", "downstream", "metric"),
        (
            "How many distinct source tables does inventory_units read?",
            "inventory_units",
            "upstream",
            "table",
        ),
        ("How many of the metrics depend on inventory?", "inventory", "downstream", "metric"),
        ("How many of those tables feed inventory_units?", "inventory_units", "upstream", "table"),
        ("How many people are maintaining inventory?", "inventory", "owner", "person"),
        ("How many metric teams maintain inventory?", "inventory", "owner", "team"),
        (
            "The tables used by inventory_units number how many?",
            "inventory_units",
            "upstream",
            "table",
        ),
        ("What is the number of reports built on inventory?", "inventory", "downstream", "view"),
        ("Which and how many views depend on inventory?", "inventory", "downstream", "view"),
        ("inventory_units reads how many source tables?", "inventory_units", "upstream", "table"),
    ],
)
def test_development_directory_count_preserves_its_requested_object_type(
    question: str, subject: str, intent: str, target: str
) -> None:
    """Quantity scope binds to catalog head nouns across modifiers and fronted positions."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert parsed.count_focus is not None
    assert parsed.count_focus.target_kind == target


@pytest.mark.parametrize(
    "question",
    [
        "inventory 的库存一共有多少件",
        "inventory 表里有多少个订单",
        "inventory 这个表里的订单数是多少",
        "inventory 给下游门店供了多少货",
        "inventory 影响了多少个客户",
        "inventory 报表里的指标值是多少",
        "inventory 来源渠道的营业额最高是多少",
        "inventory 表中哪几个订单金额最高",
        "inventory 按团队汇总的订单数量是多少",
        "维护 inventory 的团队今年处理了多少订单",
        "inventory 中业务人员有多少人",
        "inventory 里面的团队销售额合计多少",
        "inventory 指标按报表分组后的总额是多少",
        "How many orders are in the inventory table?",
        "How many customer accounts does inventory contain?",
        "How many units were supplied from inventory?",
        "How much revenue do the reports built on inventory show?",
        "How many orders did the team maintaining inventory place?",
        "What is the total number of orders in inventory?",
        "How many orders per table are recorded in inventory?",
        "Which customers have the most orders in inventory?",
        "What is the highest metric value shown for inventory?",
        "How many team members purchased items from inventory?",
        "How many people bought products from inventory?",
    ],
)
def test_development_business_quantity_does_not_become_a_directory_count(question: str) -> None:
    """Incidental catalog words and business people do not authorize knowledge cardinality."""
    assert registered_question(question, "inventory") is None
