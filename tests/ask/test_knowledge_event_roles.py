# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind conditional sources and production-purpose results without reversing owners."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("What would stop working if inventory disappeared?", "inventory", "downstream"),
        ("What would be missing if inventory were removed?", "inventory", "downstream"),
        ("If inventory were removed, which reports would fail?", "inventory", "downstream"),
        ("Without inventory, which reports would stop refreshing?", "inventory", "downstream"),
        ("inventory 停更以后\uff0c哪些看板会受影响\uff1f", "inventory", "downstream"),
        ("inventory 一旦停更\uff0c哪些看板会受到影响\uff1f", "inventory", "downstream"),
        ("inventory 这个月不再更新\uff0c哪些报表会受影响\uff1f", "inventory", "downstream"),
        ("inventory 这个月若停更\uff0c什么报表会受影响\uff1f", "inventory", "downstream"),
        ("inventory 要是不存在了\uff0c哪些报表会受到影响\uff1f", "inventory", "downstream"),
        ("如果 inventory 消失\uff0c哪些数据会无法生成\uff1f", "inventory", "downstream"),
        ("inventory is used to build which reports?", "inventory", "downstream"),
        ("Which reports is inventory used to build?", "inventory", "downstream"),
        ("inventory is used for computing which metrics?", "inventory", "downstream"),
        ("Which reports are built using inventory?", "inventory", "downstream"),
        (
            "Which source would sales_summary lose if a source disappeared?",
            "sales_summary",
            "upstream",
        ),
        (
            "If a source disappeared, what input would sales_summary lose?",
            "sales_summary",
            "upstream",
        ),
        ("Without which tables would sales_summary stop refreshing?", "sales_summary", "upstream"),
        ("Which tables would sales_summary fail without?", "sales_summary", "upstream"),
        ("sales_summary 的输入如果没了\uff0c它会缺少哪些源数据\uff1f", "sales_summary", "upstream"),
        ("如果哪些输入表没了\uff0csales_summary 会停止更新\uff1f", "sales_summary", "upstream"),
        ("Which input tables are used to build sales_summary?", "sales_summary", "upstream"),
        ("Which input tables are used when building sales_summary?", "sales_summary", "upstream"),
        ("Which input tables are used for generating sales_summary?", "sales_summary", "upstream"),
        ("Which input tables are used to produce sales_summary?", "sales_summary", "upstream"),
        ("What data is used when producing sales_summary?", "sales_summary", "upstream"),
        ("What data is used to calculate sales_summary?", "sales_summary", "upstream"),
        ("Which source tables are used to compute inventory_units?", "inventory_units", "upstream"),
        (
            "Which input tables are used for computing inventory_units?",
            "inventory_units",
            "upstream",
        ),
        ("Which data is used when calculating inventory_units?", "inventory_units", "upstream"),
        ("What inputs are used to generate inventory_units?", "inventory_units", "upstream"),
        ("Who owns inventory if it stops refreshing?", "inventory", "owner"),
        ("Which team maintains inventory when its consumers stop working?", "inventory", "owner"),
        ("Who maintains inventory after it is used to build reports?", "inventory", "owner"),
        ("Who owns inventory even if it stops feeding reports?", "inventory", "owner"),
        ("inventory 停更以后\uff0c哪个团队负责它\uff1f", "inventory", "owner"),
        ("inventory 要是没了\uff0c由谁负责恢复\uff1f", "inventory", "owner"),
        ("当 inventory 不再更新时\uff0c谁负责维护\uff1f", "inventory", "owner"),
        ("Who is responsible for inventory used to produce reports?", "inventory", "owner"),
        ("inventory 没有哪些输入\uff1f", "inventory", "upstream"),
        ("inventory 停用了哪些输入\uff1f", "inventory", "upstream"),
        ("inventory 删除了哪些源表\uff1f", "inventory", "upstream"),
        ("inventory dropped which input tables?", "inventory", "upstream"),
        ("inventory missing which inputs?", "inventory", "upstream"),
        ("What input tables did inventory drop?", "inventory", "upstream"),
        ("Which inputs is inventory missing?", "inventory", "upstream"),
        ("inventory removes which input tables?", "inventory", "upstream"),
        ("What data is used to compute reports from inventory?", "inventory", "downstream"),
        ("What data is used to calculate metrics using inventory?", "inventory", "downstream"),
        ("Which outputs are used to build reports with inventory?", "inventory", "downstream"),
        (
            "Which reports are used to build a dashboard fed by inventory?",
            "inventory",
            "downstream",
        ),
        (
            "Which source tables are used to compute the inventory_units metric?",
            "inventory_units",
            "upstream",
        ),
        ("What data is used to build the sales_summary view?", "sales_summary", "upstream"),
        ("Which tables does inventory read to build reports?", "inventory", "upstream"),
        ("Which tables has inventory used to build reports?", "inventory", "upstream"),
        ("Which tables is inventory used to build?", "inventory", "downstream"),
        ("Which tables has inventory been used to build?", "inventory", "downstream"),
        ("Which tables is inventory read to build?", "inventory", "downstream"),
        ("inventory has used which tables to build reports?", "inventory", "upstream"),
        ("inventory has been used to build which reports?", "inventory", "downstream"),
        ("inventory reads which tables to build reports?", "inventory", "upstream"),
        ("Which tables was inventory used to build?", "inventory", "downstream"),
        ("Which tables does inventory use to build reports?", "inventory", "upstream"),
        ("inventory is read to build which reports?", "inventory", "downstream"),
        ("Which tables is inventory actually used to build?", "inventory", "downstream"),
        ("inventory\uff0c如果没了\uff0c哪些表会受影响\uff1f", "inventory", "downstream"),
        ("如果 inventory 没了\uff0c哪些表会受影响\uff1f", "inventory", "downstream"),
        ("inventory\uff0c如果哪些输入表没了\uff0c它会无法更新\uff1f", "inventory", "upstream"),
        ("inventory\uff0c若被删掉了\uff0c哪些表会受影响\uff1f", "inventory", "downstream"),
        ("inventory 停更以后\uff0c输入表有哪些\uff1f", "inventory", "upstream"),
        ("inventory 停更以后\uff0c哪些源表给它供数\uff1f", "inventory", "upstream"),
        ("inventory 停更以后\uff0c会影响哪些报表\uff1f", "inventory", "downstream"),
        ("inventory 停更以后\uff0c哪个团队负责维护它\uff1f", "inventory", "owner"),
    ],
)
def test_event_and_purpose_arguments_keep_the_queried_relationship(
    question: str, subject: str, intent: str
) -> None:
    """Condition scope and direct complements preserve source, result and owner roles."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].name == subject
