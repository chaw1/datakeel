# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise ordinary bilingual questions with isolated typed development identities."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("inventory_units 在使用中由谁负责", "inventory_units", "owner"),
        ("谁在使用由团队负责的 inventory_units", "inventory_units", "downstream"),
        ("Who builds inventory_units from reports?", "inventory_units", "upstream"),
        ("Who owns inventory_units built from reports?", "inventory_units", "owner"),
        ("Who supplies inventory_units?", "inventory_units", "upstream"),
        ("Who maintains inventory_units?", "inventory_units", "owner"),
        ("谁给 inventory_units 供数", "inventory_units", "upstream"),
        ("谁负责 inventory_units", "inventory_units", "owner"),
        ("inventory_units 由谁生成", "inventory_units", "upstream"),
        ("inventory_units 由谁维护", "inventory_units", "owner"),
        ("Who are the sources for inventory_units?", "inventory_units", "upstream"),
        ("Who are the owners of inventory_units?", "inventory_units", "owner"),
        ("Who uses inventory_units?", "inventory_units", "downstream"),
        ("Who owns inventory_units?", "inventory_units", "owner"),
        ("谁在用 inventory_units", "inventory_units", "downstream"),
        ("谁在管 inventory_units", "inventory_units", "owner"),
        ("Which teams consume inventory_units?", "inventory_units", "downstream"),
        ("Which teams manage inventory_units?", "inventory_units", "owner"),
        ("inventory_units 被哪些团队调用", "inventory_units", "downstream"),
        ("inventory_units 被哪些团队维护", "inventory_units", "owner"),
        ("What does inventory_units feed?", "inventory_units", "downstream"),
        ("What feeds inventory_units?", "inventory_units", "upstream"),
        ("What does inventory_units use?", "inventory_units", "upstream"),
        ("What uses inventory_units?", "inventory_units", "downstream"),
        ("inventory_units 支撑的是哪些表", "inventory_units", "downstream"),
        ("支撑 inventory_units 的是哪些表", "inventory_units", "upstream"),
        ("inventory_units 来自什么", "inventory_units", "upstream"),
        ("来自 inventory_units 的是什么", "inventory_units", "downstream"),
        ("inventory_units is built from what?", "inventory_units", "upstream"),
        ("What is built from inventory_units?", "inventory_units", "downstream"),
        ("What are the metrics related to sales_summary?", "sales_summary", "downstream"),
        ("What are the tables related to sales_summary?", "sales_summary", "upstream"),
        ("sales_summary 关联的指标具体是什么", "sales_summary", "downstream"),
        ("sales_summary 关联的底表具体是什么", "sales_summary", "upstream"),
        ("What are the teams responsible for orders?", "orders", "owner"),
        ("What are the teams using orders?", "orders", "downstream"),
        ("负责 orders 的团队都是什么", "orders", "owner"),
        ("使用 orders 的团队都是什么", "orders", "downstream"),
        ("Who maintains inventory_units, the upstream metric?", "inventory_units", "owner"),
        ("Who uses inventory_units, the upstream metric?", "inventory_units", "downstream"),
        ("Who maintains inventory_units, a downstream metric?", "inventory_units", "owner"),
        ("这个上游指标 inventory_units 由谁负责", "inventory_units", "owner"),
        ("谁维护 inventory_units 这个下游指标", "inventory_units", "owner"),
        ("Who is responsible for reading inventory_units?", "inventory_units", "owner"),
        ("Who is reading inventory_units?", "inventory_units", "downstream"),
        ("Who feeds inventory_units?", "inventory_units", "upstream"),
        ("Which teams generate inventory_units?", "inventory_units", "upstream"),
        ("Which teams maintain inventory_units?", "inventory_units", "owner"),
        ("Who feeds reports with inventory_units?", "inventory_units", "downstream"),
        ("Who feeds inventory_units with reports?", "inventory_units", "upstream"),
        ("What tables feed dashboards with inventory_units?", "inventory_units", "downstream"),
        ("What tables feed inventory_units with data?", "inventory_units", "upstream"),
        ("inventory_units feeds which reports with data?", "inventory_units", "downstream"),
        ("Which reports feed inventory_units with data?", "inventory_units", "upstream"),
        ("Which reports are fed with inventory_units?", "inventory_units", "downstream"),
        ("inventory_units is fed with which reports?", "inventory_units", "upstream"),
        ("inventory_units 的下游是哪些使用它的表", "inventory_units", "downstream"),
        ("inventory_units 的上游是哪些被它使用的表", "inventory_units", "upstream"),
        ("Which reports does inventory_units supply with data?", "inventory_units", "downstream"),
        ("Which reports supply inventory_units with data?", "inventory_units", "upstream"),
        ("Who produces reports using inventory_units?", "inventory_units", "downstream"),
        ("Who produces inventory_units using reports?", "inventory_units", "upstream"),
        ("What reports are produced using inventory_units?", "inventory_units", "downstream"),
        ("inventory_units is produced using what reports?", "inventory_units", "upstream"),
        ("Which tables build reports from inventory_units?", "inventory_units", "downstream"),
        ("Which tables build inventory_units from reports?", "inventory_units", "upstream"),
        ("What reports are built from inventory_units?", "inventory_units", "downstream"),
        ("inventory_units is built from what reports?", "inventory_units", "upstream"),
        ("Using inventory_units, which tables produce reports?", "inventory_units", "downstream"),
        ("Using what tables do reports produce inventory_units?", "inventory_units", "upstream"),
        ("From inventory_units, what tables are built?", "inventory_units", "downstream"),
        ("From what tables is inventory_units built?", "inventory_units", "upstream"),
        ("inventory_units supplies inputs to which reports?", "inventory_units", "downstream"),
        ("Which reports supply inputs to inventory_units?", "inventory_units", "upstream"),
        ("Which reports receive inputs from inventory_units?", "inventory_units", "downstream"),
        ("inventory_units receives inputs from which reports?", "inventory_units", "upstream"),
        ("哪些表用 inventory_units 生成报表", "inventory_units", "downstream"),
        ("哪些表用报表生成 inventory_units", "inventory_units", "upstream"),
        ("用 inventory_units 生成的表有哪些", "inventory_units", "downstream"),
        ("用哪些表生成 inventory_units", "inventory_units", "upstream"),
        ("哪些表拿 inventory_units 生成报表", "inventory_units", "downstream"),
        ("哪些表拿报表生成 inventory_units", "inventory_units", "upstream"),
        ("拿 inventory_units 生成哪些表", "inventory_units", "downstream"),
        ("拿哪些表生成 inventory_units", "inventory_units", "upstream"),
        ("inventory 为哪些表供数", "inventory", "downstream"),
        ("哪些表为 inventory 供数", "inventory", "upstream"),
        ("inventory 由哪些表供数", "inventory", "upstream"),
        ("由 inventory 供数的有哪些", "inventory", "downstream"),
        ("inventory 对应哪些表", "inventory", "related"),
        ("sales_summary 对应哪些报表", "sales_summary", "related"),
        ("Who maintains inventory?", "inventory", "owner"),
        ("Who is the owner of inventory used to build reports?", "inventory", "owner"),
        ("负责 inventory 的是谁", "inventory", "owner"),
        ("谁用 inventory 生成报表", "inventory", "downstream"),
        ("What tables does inventory feed reports with?", "inventory", "upstream"),
        ("What tables does inventory produce reports using?", "inventory", "upstream"),
        ("inventory_units 有哪些它曾经用过的表", "inventory_units", "upstream"),
        ("inventory_units 有哪些使用它的表", "inventory_units", "downstream"),
        ("inventory_units 有哪些表曾经使用它", "inventory_units", "downstream"),
        ("inventory_units 有多少张它使用过的表", "inventory_units", "upstream"),
        ("inventory_units 有多少张依赖它的表", "inventory_units", "downstream"),
        ("inventory_units 有哪些它依赖的表", "inventory_units", "upstream"),
    ],
)
def test_ordinary_roles_and_ownership_preserve_the_question_predicate(
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
