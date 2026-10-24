# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise ordinary bilingual questions with isolated typed development identities."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("inventory 表里有多少条数据", "inventory", None),
        ("inventory 表里有多少行数据", "inventory", None),
        ("How many data rows are in inventory?", "inventory", None),
        ("How many data records are in inventory?", "inventory", None),
        ("inventory 中订单数量是什么", "inventory", None),
        ("inventory 中订单数目是什么", "inventory", None),
        ("inventory_units 的总数是什么", "inventory_units", None),
        ("What quantity do the reports built from inventory show?", "inventory", None),
        ("各负责人的 inventory_units 数量是什么", "inventory_units", None),
        ("What is the quantity of inventory_units for each team?", "inventory_units", None),
        ("What is the value of inventory_units?", "inventory_units", None),
        ("What is the source of inventory_units?", "inventory_units", "upstream"),
        ("What is inventory_units' value?", "inventory_units", None),
        ("What is inventory_units' source?", "inventory_units", "upstream"),
        ("inventory_units 的数值是什么", "inventory_units", None),
        ("inventory_units 的来源是什么", "inventory_units", "upstream"),
        ("inventory_units 的指标值是什么", "inventory_units", None),
        ("inventory_units 的来源表是什么", "inventory_units", "upstream"),
        ("What is the current reading of inventory_units?", "inventory_units", None),
        ("What tables read inventory_units?", "inventory_units", "downstream"),
        ("inventory_units 的读数是多少", "inventory_units", None),
        ("哪些表读取 inventory_units", "inventory_units", "downstream"),
        ("What is the amount of 退款额?", "退款额", None),
        ("What data supplies 退款额?", "退款额", "upstream"),
        ("退款额 的金额是什么", "退款额", None),
        ("退款额 是从哪里来的", "退款额", "upstream"),
        ("What is the quantity of inventory_units?", "inventory_units", None),
        ("What are the tables used by inventory_units?", "inventory_units", "upstream"),
        ("inventory_units 的数量是什么", "inventory_units", None),
        ("inventory_units 用到的表有哪些", "inventory_units", "upstream"),
        ("Show the value of inventory_units", "inventory_units", None),
        ("Show the sources of inventory_units", "inventory_units", "upstream"),
        ("给我看看 inventory_units 的数值", "inventory_units", None),
        ("给我看看 inventory_units 的上游", "inventory_units", "upstream"),
        ("What is inventory_units?", "inventory_units", "related"),
        ("How is inventory_units calculated?", "inventory_units", "upstream"),
        ("inventory_units 是什么", "inventory_units", "related"),
        ("inventory_units 是怎么算的", "inventory_units", "upstream"),
        ("What is the formula for inventory_units?", "inventory_units", "upstream"),
        ("What is the value of inventory_units this month?", "inventory_units", None),
        ("inventory_units 的计算公式是什么", "inventory_units", "upstream"),
        ("inventory_units 本月的数值是什么", "inventory_units", None),
        ("How many teams own inventory_units?", "inventory_units", "owner"),
        ("What is the value of inventory_units for each team?", "inventory_units", None),
        ("inventory_units 的负责人有几个人", "inventory_units", "owner"),
        ("各负责人的 inventory_units 数值是什么", "inventory_units", None),
        ("What tables feed the value of inventory_units?", "inventory_units", "upstream"),
        ("inventory_units 数值来自哪些表", "inventory_units", "upstream"),
        ("inventory_units 的指标值由谁负责", "inventory_units", "owner"),
        ("What value does inventory_units have?", "inventory_units", None),
        ("inventory_units has what value?", "inventory_units", None),
        ("The value of inventory_units is what?", "inventory_units", None),
        ("The source of inventory_units is what?", "inventory_units", "upstream"),
        ("inventory_units 的值是什么", "inventory_units", None),
        ("inventory_units 的源头是什么", "inventory_units", "upstream"),
        ("What reading does inventory_units show?", "inventory_units", None),
        ("What is inventory_units reading?", "inventory_units", "upstream"),
        ("Where does the value of inventory_units come from?", "inventory_units", "upstream"),
        ("What is the source of the value of inventory_units?", "inventory_units", "upstream"),
        ("Who owns the value of inventory_units?", "inventory_units", "owner"),
        ("Who supplies the value of inventory_units?", "inventory_units", "upstream"),
        ("How is the value of inventory_units calculated?", "inventory_units", "upstream"),
        ("What is the value of inventory_units based on?", "inventory_units", "upstream"),
        ("inventory_units 的数值是怎么算出来的", "inventory_units", "upstream"),
        ("What is the reading of inventory_units?", "inventory_units", None),
        ("What is reading inventory_units?", "inventory_units", "downstream"),
        ("What is inventory_units's reading?", "inventory_units", None),
        ("Who is reading inventory_units?", "inventory_units", "downstream"),
    ],
)
def test_explicit_values_and_value_relations_keep_distinct_routes(
    question: str, subject: str, intent: str | None
) -> None:
    """Resolve the requested relation or value without promoting incidental nouns."""
    parsed = registered_question(question, subject)
    if intent is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed.intent == intent
    assert bool(parsed.intent_candidates) == (intent == "related")
    assert parsed.candidates[0].name == subject


@pytest.mark.parametrize(
    "question",
    [
        "orders 关联的指标数量是什么",
        "orders 相关指标的数目是什么",
        "orders 相关指标的总数是什么",
        "What is the quantity of metrics that use orders?",
        "What is the quantity of metrics related to orders?",
    ],
)
def test_quantity_of_catalog_metrics_preserves_counted_focus(question: str) -> None:
    """Count the quantity phrase's catalog head while keeping a numeric noun distinct."""
    parsed = registered_question(question, "orders")
    assert parsed is not None
    assert parsed.intent == "downstream"
    assert parsed.count_focus is not None
    assert parsed.count_focus.counted
    assert parsed.count_focus.target_kind == "metric"


def test_data_object_quantity_retains_catalog_count() -> None:
    """A catalog data object count remains separate from stored row and record counts."""
    parsed = registered_question("inventory 有几个下游数据对象", "inventory")
    assert parsed is not None
    assert parsed.intent == "downstream"
    assert parsed.count_focus is not None
    assert parsed.count_focus.counted
    assert parsed.count_focus.target_kind == "data"
