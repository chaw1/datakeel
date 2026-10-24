# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep grouped metric values and the question following a modifier on their own routes."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("kind", "subject", "question"),
    [
        ("metric", "inventory_units", "What is the average inventory_units this month?"),
        ("metric", "inventory_units", "What is inventory_units for the owner named Morgan?"),
        ("metric", "销售总额", "把销售总额按负责人分组。"),
        ("metric", "inventory_units", "What is the mean of inventory_units?"),
        ("metric", "inventory_units", "What was inventory_units yesterday?"),
        ("metric", "inventory_units", "What is inventory_units today?"),
        ("metric", "inventory_units", "What is the sum of inventory_units by region?"),
        ("metric", "库存量", "库存量按地区分组\uff0c列出件数。"),
        ("metric", "库存量", "库存量按地区分组\uff0c给出金额。"),
        ("metric", "库存量", "被周报使用的库存量\uff0c昨天有多少\uff1f"),
        ("metric", "库存量", "用于日报的库存量有多少\uff1f"),
        ("metric", "inventory_units", "Which regions have inventory_units less than 100?"),
        ("metric", "库存量", "哪些地区的库存量低于三百\uff1f"),
        ("metric", "库存量", "哪些地区的库存量比去年减少了\uff1f"),
        ("metric", "inventory_units", "What is inventory_units for reports named daily?"),
        ("metric", "inventory_units", "What is inventory_units by owner?"),
        ("knowledge", "inventory_units", "What is inventory_units?"),
        ("knowledge", "inventory_units", "What is inventory_units for?"),
        ("knowledge", "inventory_units", "What is inventory_units by which team?"),
        ("knowledge", "inventory_units", "What is the source of inventory_units by region?"),
        ("knowledge", "inventory_units", "What is the owner of inventory_units for each report?"),
        ("knowledge", "inventory_units", "What is the formula for inventory_units?"),
        ("knowledge", "inventory_units", "What is total inventory_units's source?"),
        ("knowledge", "inventory_units", "What is total inventory_units's owner?"),
        ("knowledge", "inventory_units", "Which tables have inventory_units greater than 500?"),
        (
            "knowledge",
            "inventory_units",
            "Which reports that use inventory_units have totals greater than 500?",
        ),
        ("knowledge", "inventory_units", "How many teams use inventory_units by region?"),
        ("knowledge", "inventory_units", "How many tables supply inventory_units?"),
        (
            "knowledge",
            "inventory_units",
            "Which source tables feed inventory_units for each region?",
        ),
        ("knowledge", "库存量", "库存量超过五百时\uff0c哪些报表会受影响\uff1f"),
        ("knowledge", "库存量", "库存量按地区汇总后\uff0c由谁负责\uff1f"),
        ("knowledge", "库存量", "按地区统计的库存量由谁维护\uff1f"),
        ("knowledge", "库存量", "库存量按地区统计的口径归哪个团队\uff1f"),
        ("knowledge", "库存量", "按地区汇总的库存量来自哪些表\uff1f"),
        ("knowledge", "库存量", "按地区统计的库存量有几张来源表\uff1f"),
        ("knowledge", "库存量", "按地区使用库存量的团队有几个\uff1f"),
        ("knowledge", "库存量", "库存量的输入数据表数量是多少\uff1f"),
        ("knowledge", "库存量", "库存量的上游来源有多少张表\uff1f"),
        ("knowledge", "库存量", "库存量被多少个报表使用\uff1f"),
        ("knowledge", "库存量", "库存量按区域汇总时依赖哪些表\uff1f"),
    ],
)
def test_grouped_value_and_knowledge_question_boundaries(
    kind: str, subject: str, question: str
) -> None:
    """Numerical main predicates stay separate from owner, source and catalog counts."""
    parsed = registered_question(question, subject)
    assert ("knowledge" if parsed else "metric") == kind
