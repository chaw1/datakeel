# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise catalog hierarchy, source roles and quantity boundaries from a development set."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent", "target"),
    [
        ("sales_summary 和哪些底表有关系", "sales_summary", "upstream", "table"),
        ("orders 关联的看板都有什么", "orders", "downstream", "view"),
        ("orders 表上有哪些汇总", "orders", "downstream", "view"),
        ("orders 相关报表列出来有哪些", "orders", "downstream", "view"),
        ("What reports are associated with orders?", "orders", "downstream", "view"),
        ("Which summaries belong with orders?", "orders", "downstream", "view"),
        ("inventory_units 对应的视图有哪些", "inventory_units", "upstream", "view"),
        ("What data relates to inventory_units?", "inventory_units", "upstream", "data"),
        ("sales_summary 相关的指标都有哪些", "sales_summary", "downstream", "metric"),
        ("跟 orders 表有关的输入指标有哪些", "orders", "downstream", "metric"),
        ("orders 表的来源指标有哪些", "orders", "upstream", "metric"),
        ("sales_summary 的数据是哪份", "sales_summary", "upstream", "data"),
        ("view sales_summary 对应的 metrics 都有哪些", "sales_summary", "downstream", "metric"),
        ("表 inventory 对应的报表有哪些", "inventory", "downstream", "view"),
        ("Which views depend on inventory_units?", "inventory_units", "downstream", "view"),
    ],
)
def test_catalog_type_focus_and_levels_compose(
    question: str, subject: str, intent: str, target: str
) -> None:
    """A nonadjacent noun supplies focus and weak source words cannot invert known levels."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert all("§" not in words for words in parsed.recognition.direction_text)
    assert parsed.recognition.direction == intent
    assert parsed.recognition.focus == ("metric" if target == "metric" else "table")


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("以 inventory_units 为基础的是哪些表", "inventory_units", "downstream"),
        ("哪些表拿 inventory_units 当输入", "inventory_units", "downstream"),
        ("把 inventory_units 作为依据的表有哪些", "inventory_units", "downstream"),
        ("用 inventory_units 当作来源的有哪些", "inventory_units", "downstream"),
        ("What uses inventory_units as an input?", "inventory_units", "downstream"),
        ("Which tables take inventory_units as a basis?", "inventory_units", "downstream"),
        ("Which tables treat inventory_units as the source?", "inventory_units", "downstream"),
        ("inventory_units serves as input for what?", "inventory_units", "downstream"),
        ("inventory_units is the input to which tables?", "inventory_units", "downstream"),
        ("Which tables are fed by inventory_units?", "inventory_units", "downstream"),
        ("What is inventory_units fed by?", "inventory_units", "upstream"),
        ("哪些表从 inventory_units 出来", "inventory_units", "downstream"),
        ("来自 inventory_units 的表有哪些", "inventory_units", "downstream"),
        ("What pulls from inventory_units?", "inventory_units", "downstream"),
        ("What does inventory_units pull from?", "inventory_units", "upstream"),
        ("谁在调用 orders", "orders", "downstream"),
        ("读取 orders 的是谁", "orders", "downstream"),
        ("Who subscribes to orders?", "orders", "downstream"),
        ("Who does inventory_units depend on?", "inventory_units", "upstream"),
        ("Who maintains inventory_units?", "inventory_units", "owner"),
    ],
)
def test_input_and_result_roles_override_asset_level(
    question: str, subject: str, intent: str
) -> None:
    """The same verb identifies opposite sides when the registered subject changes role."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("sales_summary 上一层有哪些", "upstream"),
        ("What is underneath sales_summary?", "upstream"),
        ("What does sales_summary support?", "downstream"),
        ("sales_summary 的去向有哪些", "downstream"),
        ("sales_summary 的下一站有什么", "downstream"),
        ("sales_summary 会影响哪些表", "downstream"),
        ("哪些表的变化会影响 sales_summary", "upstream"),
        ("What affects sales_summary?", "upstream"),
        ("What does sales_summary affect?", "downstream"),
        ("What is affected by sales_summary?", "downstream"),
        ("What is sales_summary affected by?", "upstream"),
        ("sales_summary 受哪些表影响", "upstream"),
        ("哪些表受 sales_summary 影响", "downstream"),
        ("如果 sales_summary 消失了,哪些表会受牵连", "downstream"),
        ("要是 sales_summary 下线会怎样", "downstream"),
        ("What breaks if sales_summary disappears?", "downstream"),
        ("What would fail without sales_summary?", "downstream"),
        ("If sales_summary were removed, what would break?", "downstream"),
    ],
)
def test_hierarchy_flow_and_impact_terms_keep_subject_roles(question: str, intent: str) -> None:
    """Impact direction is compositional while counterfactual removal asks for dependants."""
    parsed = registered_question(question, "sales_summary")
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("question", "subject", "intent", "target"),
    [
        ("orders 有几个指标在使用", "orders", "downstream", "metric"),
        ("orders 被多少个指标引用", "orders", "downstream", "metric"),
        ("inventory_units 用了多少张表", "inventory_units", "upstream", "table"),
        ("orders 关联几个看板", "orders", "downstream", "view"),
        ("How many views use orders?", "orders", "downstream", "view"),
        ("How many people maintain orders?", "orders", "owner", "person"),
        ("多少个团队维护 orders", "orders", "owner", "team"),
        ("How many teams own orders?", "orders", "owner", "team"),
        ("How many tables does Morgan own?", "Morgan", "owned", "table"),
        ("orders 下游的指标一共有多少个", "orders", "downstream", "metric"),
        ("Metrics fed by orders - how many are there?", "orders", "downstream", "metric"),
    ],
)
def test_catalog_count_carries_exact_target_to_answering(
    question: str, subject: str, intent: str, target: str
) -> None:
    """Directory counts are knowledge requests with a typed object filter, never metric SQL."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.count_focus is not None
    assert parsed.count_focus.counted
    assert parsed.count_focus.target_kind == target


@pytest.mark.parametrize(
    "question",
    [
        "How many orders were placed?",
        "How many orders does Morgan own?",
        "订单数是多少",
        "来源渠道有多少订单",
        "inventory_units 有多少",
        "Which owner manages the most orders?",
        "How many orders are stored in tables?",
        "How much revenue is shown on dashboards?",
        "几个订单会出现在报表里",
        "Which metrics report how many orders?",
    ],
)
def test_business_measure_counts_keep_metric_route(question: str) -> None:
    """Catalog vocabulary elsewhere in a sentence does not turn business counts into lists."""
    assert registered_question(question, "inventory_units") is None
